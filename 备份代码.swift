//曲线界面左右加边距功能

// 1、在 ChartView 结构体开头添加水平边距常量（与垂直边距常量一起）
private let verticalPadding: CGFloat = 20    // 上下边距
private let horizontalPadding: CGFloat = 16   // 左右边距

// 2、接下来可以整个替换，也可以逐个修改
Canvas { context, size in
    // 考虑边距后的实际绘制高度
    let effectiveHeight = size.height - (verticalPadding * 2)
    let effectiveWidth = size.width - (horizontalPadding * 2)
    
    // 修改所有 y 坐标计算，加入边距因素
    let priceToY: (Double) -> CGFloat = { price in
        let normalizedY = CGFloat((price - minPrice) / priceRange)
        return size.height - verticalPadding - (normalizedY * effectiveHeight)
    }
    
    // 修改所有 x 坐标计算，加入边距因素
    let indexToX: (Int) -> CGFloat = { index in
        let horizontalStep = effectiveWidth / CGFloat(max(1, sampledChartData.count - 1))
        return horizontalPadding + (CGFloat(index) * horizontalStep)
    }
    
    // 绘制价格线
    var pricePath = Path()
    if let firstPoint = sampledChartData.first {
        let firstX = indexToX(0)
        let firstY = priceToY(firstPoint.price)
        pricePath.move(to: CGPoint(x: firstX, y: firstY))
        
        for i in 1..<sampledChartData.count {
            let x = indexToX(i)
            let y = priceToY(sampledChartData[i].price)
            pricePath.addLine(to: CGPoint(x: x, y: y))
        }
    }
    
    // 绘制价格线
    context.stroke(pricePath, with: .color(chartColor), lineWidth: 2)
    
    // 绘制零线 - 当最低值小于 0 时
    if minPrice < 0 {
        let effectiveMaxPrice = max(maxPrice, 0)
        let effectiveRange = effectiveMaxPrice - minPrice
        let zeroY = size.height - verticalPadding - CGFloat((0 - minPrice) / effectiveRange) * effectiveHeight
        
        var zeroPath = Path()
        zeroPath.move(to: CGPoint(x: horizontalPadding, y: zeroY))
        zeroPath.addLine(to: CGPoint(x: size.width - horizontalPadding, y: zeroY))
        
        context.stroke(zeroPath, with: .color(Color.gray.opacity(0.5)), style: StrokeStyle(lineWidth: 1, dash: [4]))
    }
    
    // 绘制标记点
    for marker in getTimeMarkers() {
        if let index = sampledChartData.firstIndex(where: { isSameDay($0.date, marker.date) }) {
            let shouldShow = (marker.type == .global && showRedMarkers) ||
                            (marker.type == .symbol && showOrangeMarkers) ||
                            (marker.type == .earning && showBlueMarkers)
            
            if shouldShow {
                let x = indexToX(index)
                let y = priceToY(sampledChartData[index].price)
                
                let markerPath = Path(ellipseIn: CGRect(x: x - 4, y: y - 4, width: 8, height: 8))
                context.fill(markerPath, with: .color(marker.color))
            }
        }
    }
    
    // 触摸指示器相关绘制也需要使用新的 y 坐标计算方式
    if isMultiTouch {
        // 第一个触摸点
        if let firstIndex = firstTouchPointIndex, let firstPoint = firstTouchPoint {
            let x = indexToX(firstIndex)
            let y = priceToY(firstPoint.price)
            
            var linePath = Path()
            linePath.move(to: CGPoint(x: x, y: verticalPadding))
            linePath.addLine(to: CGPoint(x: x, y: size.height - verticalPadding))
            context.stroke(linePath, with: .color(Color.gray), style: StrokeStyle(lineWidth: 1, dash: [4]))
            
            let circlePath = Path(ellipseIn: CGRect(x: x - 5, y: y - 5, width: 10, height: 10))
            context.fill(circlePath, with: .color(Color.white))
            context.stroke(circlePath, with: .color(chartColor), lineWidth: 2)
        }
        
        // 第二个触摸点
        if let secondIndex = secondTouchPointIndex, let secondPoint = secondTouchPoint {
            let x = indexToX(secondIndex)
            let y = priceToY(secondPoint.price)
            
            var linePath = Path()
            linePath.move(to: CGPoint(x: x, y: verticalPadding))
            linePath.addLine(to: CGPoint(x: x, y: size.height - verticalPadding))
            context.stroke(linePath, with: .color(Color.gray), style: StrokeStyle(lineWidth: 1, dash: [4]))
            
            let circlePath = Path(ellipseIn: CGRect(x: x - 5, y: y - 5, width: 10, height: 10))
            context.fill(circlePath, with: .color(Color.white))
            context.stroke(circlePath, with: .color(chartColor), lineWidth: 2)
        }
        
        // 绘制两点之间的连线
        if let firstIndex = firstTouchPointIndex, let secondIndex = secondTouchPointIndex,
            let firstPoint = firstTouchPoint, let secondPoint = secondTouchPoint {
            let x1 = indexToX(firstIndex)
            let y1 = priceToY(firstPoint.price)
            let x2 = indexToX(secondIndex)
            let y2 = priceToY(secondPoint.price)
            
            var connectPath = Path()
            connectPath.move(to: CGPoint(x: x1, y: y1))
            connectPath.addLine(to: CGPoint(x: x2, y: y2))
            
            let lineColor = secondPoint.price >= firstPoint.price ? Color.green : Color.red
            context.stroke(connectPath, with: .color(lineColor), style: StrokeStyle(lineWidth: 1, dash: [2]))
        }
    } else if let pointIndex = draggedPointIndex {
        let x = indexToX(pointIndex)
        
        var linePath = Path()
        linePath.move(to: CGPoint(x: x, y: verticalPadding))
        linePath.addLine(to: CGPoint(x: x, y: size.height - verticalPadding))
        context.stroke(linePath, with: .color(Color.gray), style: StrokeStyle(lineWidth: 1, dash: [4]))
        
        if let point = draggedPoint {
            let y = priceToY(point.price)
            
            let circlePath = Path(ellipseIn: CGRect(x: x - 5, y: y - 5, width: 10, height: 10))
            context.fill(circlePath, with: .color(Color.white))
            context.stroke(circlePath, with: .color(chartColor), lineWidth: 2)
        }
    }
}