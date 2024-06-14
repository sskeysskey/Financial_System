class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("除数不能为零")
        return a / b

def main():
    calc = Calculator()
    while True:
        try:
            print("\n--- 简易计算器 ---")
            print("1. 加法")
            print("2. 减法")
            print("3. 乘法")
            print("4. 除法")
            print("5. 退出")
            choice = int(input("请选择操作 (1/2/3/4/5): "))

            if choice == 5:
                print("退出程序")
                break

            if choice in [1, 2, 3, 4]:
                num1 = float(input("请输入第一个数字: "))
                num2 = float(input("请输入第二个数字: "))

                if choice == 1:
                    print(f"结果: {calc.add(num1, num2)}")
                elif choice == 2:
                    print(f"结果: {calc.subtract(num1, num2)}")
                elif choice == 3:
                    print(f"结果: {calc.multiply(num1, num2)}")
                elif choice == 4:
                    print(f"结果: {calc.divide(num1, num2)}")
            else:
                print("无效的选项，请重试。")
        except ValueError as e:
            print(f"输入错误: {e}")

if __name__ == "__main__":
    main()