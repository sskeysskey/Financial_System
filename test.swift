import SwiftUI

enum ArticleFilterMode: String, CaseIterable {
    case unread = "Unread"
    case read = "Read"
}

// ==================== 单一来源列表 ====================
struct ArticleListView: View {
    let source: NewsSource
    @ObservedObject var viewModel: NewsViewModel
    @ObservedObject var resourceManager: ResourceManager

    @State private var filterMode: ArticleFilterMode = .unread
    
    // 修复 1: 使用计算属性和 Data 来持久化 Set<String>
    // 底层使用 @AppStorage 存储 Data
    @AppStorage private var expandedTimestampsData: Data
    
    // 对外暴露的计算属性，方便代码其他部分使用
    private var expandedTimestamps: Set<String> {
        get {
            // 从 Data 解码为 Set<String>
            if let decodedSet = try? JSONDecoder().decode(Set<String>.self, from: expandedTimestampsData) {
                return decodedSet
            }
            return Set<String>()
        }
        set {
            // 将 Set<String> 编码为 Data
            if let encodedData = try? JSONEncoder().encode(newValue) {
                expandedTimestampsData = encodedData
            }
        }
    }
    
    // 保存滚动位置
    @State private var scrollTarget: String?

    @State private var isSearching: Bool = false
    @State private var searchText: String = ""
    @State private var isSearchActive: Bool = false
    
    @State private var showErrorAlert = false
    @State private var errorMessage = ""
    
    @State private var isDownloadingImages = false
    @State private var downloadingMessage = ""
    
    @State private var selectedArticle: Article?
    @State private var isNavigationActive = false
    
    // 初始化时设置 AppStorage 的 key
    init(source: NewsSource, viewModel: NewsViewModel, resourceManager: ResourceManager) {
        self.source = source
        self.viewModel = viewModel
        self.resourceManager = resourceManager
        
        // 修复 1: 初始化底层的 Data 存储，而不是直接初始化 Set
        let key = "expandedTimestamps_\(source.name)"
        self._expandedTimestampsData = AppStorage(wrappedValue: Data(), key)
    }

    private var baseFilteredArticles: [Article] {
        source.articles.filter { article in
            let isReadEff = viewModel.isArticleEffectivelyRead(article)
            return (filterMode == .unread) ? !isReadEff : isReadEff
        }
    }

    private func groupedByTimestamp(_ articles: [Article]) -> [String: [Article]] {
        let initial = Dictionary(grouping: articles, by: { $0.timestamp })
        if filterMode == .read {
            return initial.mapValues { Array($0.reversed()) }
        } else {
            return initial
        }
    }

    private var groupedArticles: [String: [Article]] {
        groupedByTimestamp(baseFilteredArticles)
    }

    private func sortedTimestamps(for groups: [String: [Article]]) -> [String] {
        if filterMode == .read {
            return groups.keys.sorted(by: >)
        } else {
            return groups.keys.sorted(by: <)
        }
    }

    private var filteredArticles: [Article] {
        baseFilteredArticles
    }

    private var unreadCount: Int {
        source.articles.filter { !$0.isRead }.count
    }
    private var readCount: Int {
        source.articles.filter { $0.isRead }.count
    }

    private var searchResults: [Article] {
        guard isSearchActive, !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return []
        }
        let keyword = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return source.articles.filter { $0.topic.lowercased().contains(keyword) }
    }

    private func groupedSearchByTimestamp() -> [String: [Article]] {
        var initial = Dictionary(grouping: searchResults, by: { $0.timestamp })
        initial = initial.mapValues { Array($0.reversed()) }
        return initial
    }

    private func sortedSearchTimestamps(for groups: [String: [Article]]) -> [String] {
        return groups.keys.sorted(by: >)
    }

    var body: some View {
        VStack(spacing: 0) {
            if isSearching {
                SearchBarInline(
                    text: $searchText,
                    onCommit: {
                        isSearchActive = !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    },
                    onCancel: {
                        withAnimation {
                            isSearching = false
                            isSearchActive = false
                            searchText = ""
                        }
                        initializeExpandedStateIfNeeded()
                    }
                )
            }

            listContent
                .listStyle(PlainListStyle())
                .onAppear {
                    initializeExpandedStateIfNeeded()
                }
                .onChange(of: filterMode) { _, _ in
                    initializeExpandedStateIfNeeded()
                }
                // 修复 2: 使用 .navigationDestination 替代废弃的 NavigationLink
                .navigationDestination(isPresented: $isNavigationActive) {
                    if let article = selectedArticle {
                        ArticleContainerView(
                            article: article,
                            sourceName: source.name,
                            context: .fromSource(source.name),
                            viewModel: viewModel,
                            resourceManager: resourceManager
                        )
                    }
                }

            if !isSearchActive {
                Picker("Filter", selection: $filterMode) {
                    ForEach(ArticleFilterMode.allCases, id: \.self) { mode in
                        let count = (mode == .unread) ? unreadCount : readCount
                        Text("\(mode.rawValue) (\(count))").tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .padding([.horizontal, .bottom])
            }
        }
        .background(Color.viewBackground.ignoresSafeArea())
        // 修复 2: 移除旧的、隐藏的 NavigationLink
        .navigationTitle(source.name.replacingOccurrences(of: "_", with: " "))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task {
                        await syncResources(isManual: true)
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(resourceManager.isSyncing)
                .accessibilityLabel("刷新")
            }
            
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    withAnimation {
                        isSearching.toggle()
                        if !isSearching {
                            isSearchActive = false
                            searchText = ""
                        }
                    }
                } label: {
                    Image(systemName: "magnifyingglass")
                }
                .accessibilityLabel("搜索")
            }
        }
        .overlay(
            Group {
                if isDownloadingImages {
                    VStack(spacing: 15) {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            .scaleEffect(1.5)
                        
                        Text(downloadingMessage)
                            .padding(.top, 10)
                            .foregroundColor(.white.opacity(0.9))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.black.opacity(0.6))
                    .edgesIgnoringSafeArea(.all)
                }
            }
        )
        .alert("", isPresented: $showErrorAlert, actions: {
            Button("好的", role: .cancel) { }
        }, message: {
            Text(errorMessage)
        })
    }
    
    @ViewBuilder
    private var listContent: some View {
        ScrollViewReader { proxy in
            List {
                if isSearchActive {
                    searchResultsList
                } else {
                    articlesList
                }
            }
            .onChange(of: scrollTarget) { _, newValue in
                if let target = newValue {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        withAnimation {
                            proxy.scrollTo(target, anchor: .top)
                        }
                    }
                }
            }
        }
    }
    
    @ViewBuilder
    private var searchResultsList: some View {
        let grouped = groupedSearchByTimestamp()
        let timestamps = sortedSearchTimestamps(for: grouped)

        if searchResults.isEmpty {
            Section {
                Text("未找到匹配的文章")
                    .foregroundColor(.secondary)
                    .padding(.vertical, 12)
                    .listRowBackground(Color.clear)
            } header: {
                Text("搜索结果")
                    .font(.headline)
                    .foregroundColor(.blue.opacity(0.7))
                    .padding(.vertical, 4)
            }
        } else {
            ForEach(timestamps, id: \.self) { timestamp in
                Section(header:
                            VStack(alignment: .leading, spacing: 2) {
                                Text("搜索结果")
                                    .font(.subheadline)
                                    .foregroundColor(.blue.opacity(0.7))
                                Text("\(formatTimestamp(timestamp)) \(grouped[timestamp]?.count ?? 0)")
                                    .font(.headline)
                                    .foregroundColor(.blue.opacity(0.85))
                            }
                            .padding(.vertical, 4)
                ) {
                    ForEach(grouped[timestamp] ?? []) { article in
                        Button(action: {
                            scrollTarget = article.id.uuidString
                            Task {
                                await handleArticleTap(article)
                            }
                        }) {
                            ArticleRowCardView(
                                article: article,
                                sourceName: nil,
                                isReadEffective: viewModel.isArticleEffectivelyRead(article)
                            )
                        }
                        .id(article.id.uuidString)
                        .buttonStyle(PlainButtonStyle())
                        .listRowInsets(EdgeInsets(top: 4, leading: 6, bottom: 4, trailing: 6))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .contextMenu {
                            if article.isRead {
                                Button { viewModel.markAsUnread(articleID: article.id) }
                                label: { Label("标记为未读", systemImage: "circle") }
                            } else {
                                Button { viewModel.markAsRead(articleID: article.id) }
                                label: { Label("标记为已读", systemImage: "checkmark.circle") }
                            }
                        }
                    }
                }
            }
        }
    }
    
    @ViewBuilder
    private var articlesList: some View {
        let timestamps = sortedTimestamps(for: groupedArticles)
        ForEach(timestamps, id: \.self) { timestamp in
            Section {
                if expandedTimestamps.contains(timestamp) {
                    ForEach(groupedArticles[timestamp] ?? []) { article in
                        Button(action: {
                            scrollTarget = article.id.uuidString
                            Task {
                                await handleArticleTap(article)
                            }
                        }) {
                            ArticleRowCardView(
                                article: article,
                                sourceName: nil,
                                isReadEffective: viewModel.isArticleEffectivelyRead(article)
                            )
                        }
                        .id(article.id.uuidString)
                        .buttonStyle(PlainButtonStyle())
                        .listRowInsets(EdgeInsets(top: 4, leading: 6, bottom: 4, trailing: 6))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .contextMenu {
                            if article.isRead {
                                Button { viewModel.markAsUnread(articleID: article.id) }
                                label: { Label("标记为未读", systemImage: "circle") }
                            } else {
                                Button { viewModel.markAsRead(articleID: article.id) }
                                label: { Label("标记为已读", systemImage: "checkmark.circle") }
                                if filterMode == .unread {
                                    Divider()
                                    Button {
                                        viewModel.markAllAboveAsRead(articleID: article.id, inVisibleList: self.filteredArticles)
                                    }
                                    label: { Label("以上全部已读", systemImage: "arrow.up.to.line.compact") }

                                    Button {
                                        viewModel.markAllBelowAsRead(articleID: article.id, inVisibleList: self.filteredArticles)
                                    }
                                    label: { Label("以下全部已读", systemImage: "arrow.down.to.line.compact") }
                                }
                            }
                        }
                    }
                }
            } header: {
                HStack(spacing: 8) {
                    Text(formatTimestamp(timestamp))
                        .font(.headline)
                        .foregroundColor(.blue.opacity(0.7))

                    Spacer(minLength: 8)

                    Text("\(groupedArticles[timestamp]?.count ?? 0)")
                        .font(.subheadline)
                        .foregroundColor(.secondary)

                    Image(systemName: expandedTimestamps.contains(timestamp) ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .font(.footnote.weight(.semibold))
                }
                .padding(.vertical, 4)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        if expandedTimestamps.contains(timestamp) {
                            expandedTimestamps.remove(timestamp)
                        } else {
                            expandedTimestamps.insert(timestamp)
                        }
                    }
                }
            }
        }
    }

    private func handleArticleTap(_ article: Article) async {
        guard !article.images.isEmpty else {
            selectedArticle = article
            isNavigationActive = true
            // 预加载下一篇
            preloadNextArticleImages(after: article.id)
            return
        }
        
        await MainActor.run {
            isDownloadingImages = true
            downloadingMessage = "正在加载图片..."
        }
        
        do {
            try await resourceManager.downloadImagesForArticle(
                timestamp: article.timestamp,
                imageNames: article.images
            )
            
            await MainActor.run {
                isDownloadingImages = false
                selectedArticle = article
                isNavigationActive = true
                // 预加载下一篇
                preloadNextArticleImages(after: article.id)
            }
        } catch {
            await MainActor.run {
                isDownloadingImages = false
                errorMessage = "图片下载失败: \(error.localizedDescription)"
                showErrorAlert = true
            }
        }
    }
    
    // 预加载下一篇文章的图片
    private func preloadNextArticleImages(after currentID: UUID) {
        Task {
            if let nextItem = viewModel.findNextUnread(after: currentID, inSource: source.name) {
                let nextArticle = nextItem.article
                guard !nextArticle.images.isEmpty else { return }
                
                print("🔄 开始预加载下一篇文章的图片: \(nextArticle.topic)")
                do {
                    try await resourceManager.downloadImagesForArticle(
                        timestamp: nextArticle.timestamp,
                        imageNames: nextArticle.images
                    )
                    print("✅ 预加载完成: \(nextArticle.topic)")
                } catch {
                    print("⚠️ 预加载失败: \(error.localizedDescription)")
                }
            }
        }
    }

    private func initializeExpandedStateIfNeeded() {
        let timestamps = sortedTimestamps(for: groupedArticles)
        // 只有在第一次进入或切换模式时，且当前没有任何展开状态时，才自动展开单个分组
        if expandedTimestamps.isEmpty && timestamps.count == 1 {
            self.expandedTimestamps = Set(timestamps)
        }
    }

    private func formatTimestamp(_ timestamp: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyMMdd"
        guard let date = formatter.date(from: timestamp) else { return timestamp }
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "yyyy年M月d日, EEEE"
        return formatter.string(from: date)
    }
    
    private func syncResources(isManual: Bool = false) async {
        do {
            try await resourceManager.checkAndDownloadUpdates(isManual: isManual)
            viewModel.loadNews()
        } catch {
            if isManual {
                switch error {
                case is DecodingError:
                    self.errorMessage = "数据解析失败,请稍后重试。"
                    self.showErrorAlert = true
                case let urlError as URLError where
                    urlError.code == .cannotConnectToHost ||
                    urlError.code == .timedOut ||
                    urlError.code == .notConnectedToInternet:
                    self.errorMessage = "网络连接失败，请检查网络设置或稍后重试。"
                    self.showErrorAlert = true
                default:
                    self.errorMessage = "发生未知错误，请稍后重试。"
                    self.showErrorAlert = true
                }
                print("手动同步失败: \(error)")
            } else {
                print("自动同步静默失败: \(error)")
            }
        }
    }
}

// ==================== 所有文章列表 ====================
struct AllArticlesListView: View {
    @ObservedObject var viewModel: NewsViewModel
    @ObservedObject var resourceManager: ResourceManager

    @State private var filterMode: ArticleFilterMode = .unread

    @State private var isSearching: Bool = false
    @State private var searchText: String = ""
    @State private var isSearchActive: Bool = false

    // 修复 1: 对 AllArticlesListView 应用同样的 AppStorage 修复方案
    @AppStorage("expandedTimestamps_ALL_Data") private var expandedTimestampsData: Data = Data()
    
    private var expandedTimestamps: Set<String> {
        get {
            if let decodedSet = try? JSONDecoder().decode(Set<String>.self, from: expandedTimestampsData) {
                return decodedSet
            }
            return Set<String>()
        }
        set {
            if let encodedData = try? JSONEncoder().encode(newValue) {
                expandedTimestampsData = encodedData
            }
        }
    }
    
    @State private var scrollTarget: String?
    
    @State private var showErrorAlert = false
    @State private var errorMessage = ""
    
    @State private var isDownloadingImages = false
    @State private var downloadingMessage = ""
    
    @State private var selectedArticleItem: (article: Article, sourceName: String)?
    @State private var isNavigationActive = false

    private var baseFilteredArticles: [(article: Article, sourceName: String)] {
        viewModel.allArticlesSortedForDisplay.filter { item in
            let isReadEff = viewModel.isArticleEffectivelyRead(item.article)
            return (filterMode == .unread) ? !isReadEff : isReadEff
        }
    }

    private func groupedByTimestamp(_ items: [(article: Article, sourceName: String)]) -> [String: [(article: Article, sourceName: String)]] {
        let initial = Dictionary(grouping: items, by: { $0.article.timestamp })
        if filterMode == .read {
            return initial.mapValues { Array($0.reversed()) }
        } else {
            return initial
        }
    }

    private var groupedArticles: [String: [(article: Article, sourceName: String)]] {
        groupedByTimestamp(baseFilteredArticles)
    }

    private func sortedTimestamps(for groups: [String: [(article: Article, sourceName: String)]]) -> [String] {
        if filterMode == .read {
            return groups.keys.sorted(by: >)
        } else {
            return groups.keys.sorted(by: <)
        }
    }

    private var filteredArticles: [(article: Article, sourceName: String)] {
        baseFilteredArticles
    }

    private var totalUnreadCount: Int { viewModel.totalUnreadCount }
    private var totalReadCount: Int { viewModel.sources.flatMap { $0.articles }.filter { $0.isRead }.count }

    private var searchResults: [(article: Article, sourceName: String)] {
        guard isSearchActive, !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return []
        }
        let keyword = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return viewModel.allArticlesSortedForDisplay.filter { $0.article.topic.lowercased().contains(keyword) }
    }

    private func groupedSearchByTimestamp() -> [String: [(article: Article, sourceName: String)]] {
        var initial = Dictionary(grouping: searchResults, by: { $0.article.timestamp })
        initial = initial.mapValues { Array($0.reversed()) }
        return initial
    }

    private func sortedSearchTimestamps(for groups: [String: [(article: Article, sourceName: String)]]) -> [String] {
        return groups.keys.sorted(by: >)
    }

    var body: some View {
        VStack(spacing: 0) {
            if isSearching {
                SearchBarInline(
                    text: $searchText,
                    onCommit: {
                        isSearchActive = !searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    },
                    onCancel: {
                        withAnimation {
                            isSearching = false
                            isSearchActive = false
                            searchText = ""
                        }
                        initializeExpandedStateIfNeeded()
                    }
                )
            }

            listContent
                .listStyle(PlainListStyle())
                .onAppear {
                    initializeExpandedStateIfNeeded()
                }
                .onChange(of: filterMode) { _, _ in
                    initializeExpandedStateIfNeeded()
                }
                // 修复 2: 对 AllArticlesListView 应用同样的导航修复方案
                .navigationDestination(isPresented: $isNavigationActive) {
                    if let item = selectedArticleItem {
                        ArticleContainerView(
                            article: item.article,
                            sourceName: item.sourceName,
                            context: .fromAllArticles,
                            viewModel: viewModel,
                            resourceManager: resourceManager
                        )
                    }
                }

            if !isSearchActive {
                Picker("Filter", selection: $filterMode) {
                    ForEach(ArticleFilterMode.allCases, id: \.self) { mode in
                        let count = (mode == .unread) ? totalUnreadCount : totalReadCount
                        Text("\(mode.rawValue) (\(count))").tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .padding([.horizontal, .bottom])
            }
        }
        .background(Color.viewBackground.ignoresSafeArea())
        // 修复 2: 移除旧的、隐藏的 NavigationLink
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task {
                        await syncResources(isManual: true)
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(resourceManager.isSyncing)
                .accessibilityLabel("刷新")
            }
            
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    withAnimation {
                        isSearching.toggle()
                        if !isSearching {
                            isSearchActive = false
                            searchText = ""
                        }
                    }
                } label: {
                    Image(systemName: "magnifyingglass")
                }
                .accessibilityLabel("搜索")
            }
        }
        .overlay(
            Group {
                if isDownloadingImages {
                    VStack(spacing: 15) {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            .scaleEffect(1.5)
                        
                        Text(downloadingMessage)
                            .padding(.top, 10)
                            .foregroundColor(.white.opacity(0.9))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.black.opacity(0.6))
                    .edgesIgnoringSafeArea(.all)
                }
            }
        )
        .alert("", isPresented: $showErrorAlert, actions: {
            Button("好的", role: .cancel) { }
        }, message: {
            Text(errorMessage)
        })
    }
    
    @ViewBuilder
    private var listContent: some View {
        ScrollViewReader { proxy in
            List {
                if isSearchActive {
                    searchResultsList
                } else {
                    articlesList
                }
            }
            .onChange(of: scrollTarget) { _, newValue in
                if let target = newValue {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        withAnimation {
                            proxy.scrollTo(target, anchor: .top)
                        }
                    }
                }
            }
        }
    }
    
    @ViewBuilder
    private var searchResultsList: some View {
        let grouped = groupedSearchByTimestamp()
        let timestamps = sortedSearchTimestamps(for: grouped)

        if searchResults.isEmpty {
            Section {
                Text("未找到匹配的文章")
                    .foregroundColor(.secondary)
                    .padding(.vertical, 12)
                    .listRowBackground(Color.clear)
            } header: {
                Text("搜索结果")
                    .font(.headline)
                    .foregroundColor(.blue.opacity(0.7))
                    .padding(.vertical, 4)
            }
        } else {
            ForEach(timestamps, id: \.self) { timestamp in
                Section(header:
                            VStack(alignment: .leading, spacing: 2) {
                                Text("搜索结果")
                                    .font(.subheadline)
                                    .foregroundColor(.blue.opacity(0.7))
                                Text("\(formatTimestamp(timestamp)) \(grouped[timestamp]?.count ?? 0)")
                                    .font(.headline)
                                    .foregroundColor(.blue.opacity(0.85))
                            }
                            .padding(.vertical, 4)
                ) {
                    ForEach(grouped[timestamp] ?? [], id: \.article.id) { item in
                        Button(action: {
                            scrollTarget = item.article.id.uuidString
                            Task {
                                await handleArticleTap(item)
                            }
                        }) {
                            ArticleRowCardView(
                                article: item.article,
                                sourceName: item.sourceName,
                                isReadEffective: viewModel.isArticleEffectivelyRead(item.article)
                            )
                        }
                        .id(item.article.id.uuidString)
                        .buttonStyle(PlainButtonStyle())
                        .listRowInsets(EdgeInsets(top: 4, leading: 6, bottom: 4, trailing: 6))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .contextMenu {
                            if item.article.isRead {
                                Button { viewModel.markAsUnread(articleID: item.article.id) }
                                label: { Label("标记为未读", systemImage: "circle") }
                            } else {
                                Button { viewModel.markAsRead(articleID: item.article.id) }
                                label: { Label("标记为已读", systemImage: "checkmark.circle") }
                            }
                        }
                    }
                }
            }
        }
    }
    
    @ViewBuilder
    private var articlesList: some View {
        let timestamps = sortedTimestamps(for: groupedArticles)
        ForEach(timestamps, id: \.self) { timestamp in
            Section {
                if expandedTimestamps.contains(timestamp) {
                    ForEach(groupedArticles[timestamp] ?? [], id: \.article.id) { item in
                        Button(action: {
                            scrollTarget = item.article.id.uuidString
                            Task {
                                await handleArticleTap(item)
                            }
                        }) {
                            ArticleRowCardView(
                                article: item.article,
                                sourceName: item.sourceName,
                                isReadEffective: viewModel.isArticleEffectivelyRead(item.article)
                            )
                        }
                        .id(item.article.id.uuidString)
                        .buttonStyle(PlainButtonStyle())
                        .listRowInsets(EdgeInsets(top: 4, leading: 6, bottom: 4, trailing: 6))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .contextMenu {
                            if item.article.isRead {
                                Button { viewModel.markAsUnread(articleID: item.article.id) }
                                label: { Label("标记为未读", systemImage: "circle") }
                            } else {
                                Button { viewModel.markAsRead(articleID: item.article.id) }
                                label: { Label("标记为已读", systemImage: "checkmark.circle") }
                                if filterMode == .unread {
                                    Divider()
                                    Button {
                                        let visibleArticleList = self.filteredArticles.map { $0.article }
                                        viewModel.markAllAboveAsRead(articleID: item.article.id, inVisibleList: visibleArticleList)
                                    }
                                    label: { Label("以上全部已读", systemImage: "arrow.up.to.line.compact") }

                                    Button {
                                        let visibleArticleList = self.filteredArticles.map { $0.article }
                                        viewModel.markAllBelowAsRead(articleID: item.article.id, inVisibleList: visibleArticleList)
                                    }
                                    label: { Label("以下全部已读", systemImage: "arrow.down.to.line.compact") }
                                }
                            }
                        }
                    }
                }
            } header: {
                HStack(spacing: 8) {
                    Text(formatTimestamp(timestamp))
                        .font(.headline)
                        .foregroundColor(.blue.opacity(0.7))

                    Spacer(minLength: 8)

                    Text("\(groupedArticles[timestamp]?.count ?? 0)")
                        .font(.subheadline)
                        .foregroundColor(.secondary)

                    Image(systemName: expandedTimestamps.contains(timestamp) ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .font(.footnote.weight(.semibold))
                }
                .padding(.vertical, 4)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        var mutableSet = self.expandedTimestamps
                        if mutableSet.contains(timestamp) {
                            mutableSet.remove(timestamp)
                        } else {
                            mutableSet.insert(timestamp)
                        }
                        self.expandedTimestamps = mutableSet
                    }
                }
            }
        }
    }

    private func handleArticleTap(_ item: (article: Article, sourceName: String)) async {
        guard !item.article.images.isEmpty else {
            selectedArticleItem = item
            isNavigationActive = true
            preloadNextArticleImages(after: item.article.id)
            return
        }
        
        await MainActor.run {
            isDownloadingImages = true
            downloadingMessage = "正在加载图片..."
        }
        
        do {
            try await resourceManager.downloadImagesForArticle(
                timestamp: item.article.timestamp,
                imageNames: item.article.images
            )
            
            await MainActor.run {
                isDownloadingImages = false
                selectedArticleItem = item
                isNavigationActive = true
                preloadNextArticleImages(after: item.article.id)
            }
        } catch {
            await MainActor.run {
                isDownloadingImages = false
                errorMessage = "图片下载失败: \(error.localizedDescription)"
                showErrorAlert = true
            }
        }
    }
    
    private func preloadNextArticleImages(after currentID: UUID) {
        Task {
            if let nextItem = viewModel.findNextUnread(after: currentID, inSource: nil) {
                let nextArticle = nextItem.article
                guard !nextArticle.images.isEmpty else { return }
                
                print("🔄 开始预加载下一篇文章的图片: \(nextArticle.topic)")
                do {
                    try await resourceManager.downloadImagesForArticle(
                        timestamp: nextArticle.timestamp,
                        imageNames: nextArticle.images
                    )
                    print("✅ 预加载完成: \(nextArticle.topic)")
                } catch {
                    print("⚠️ 预加载失败: \(error.localizedDescription)")
                }
            }
        }
    }

    private func initializeExpandedStateIfNeeded() {
        let timestamps = sortedTimestamps(for: groupedArticles)
        if expandedTimestamps.isEmpty && timestamps.count == 1 {
            var mutableSet = self.expandedTimestamps
            mutableSet = Set(timestamps)
            self.expandedTimestamps = mutableSet
        }
    }

    private func formatTimestamp(_ timestamp: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyMMdd"
        guard let date = formatter.date(from: timestamp) else { return timestamp }
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "yyyy年M月d日, EEEE"
        return formatter.string(from: date)
    }
    
    private func syncResources(isManual: Bool = false) async {
        do {
            try await resourceManager.checkAndDownloadUpdates(isManual: isManual)
            viewModel.loadNews()
        } catch {
            if isManual {
                switch error {
                case is DecodingError:
                    self.errorMessage = "数据解析失败，请稍后重试。"
                    self.showErrorAlert = true
                case let urlError as URLError where
                    urlError.code == .cannotConnectToHost ||
                    urlError.code == .timedOut ||
                    urlError.code == .notConnectedToInternet:
                    self.errorMessage = "网络连接失败，请检查网络设置或稍后重试。"
                    self.showErrorAlert = true
                default:
                    self.errorMessage = "发生未知错误，请稍后重试。"
                    self.showErrorAlert = true
                }
                print("手动同步失败: \(error)")
            } else {
                print("自动同步静默失败: \(error)")
            }
        }
    }
}