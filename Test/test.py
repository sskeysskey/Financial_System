import tkinter as tk
root = tk.Tk()
root.title("Test Tkinter")
root.geometry("200x100")
label = tk.Label(root, text="Tkinter is working!")
label.pack()
root.mainloop()