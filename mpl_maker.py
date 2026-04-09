import tkinter as tk

def show_deprecated():
    root = tk.Tk()
    root.title("MPL Maker - 서비스 종료")
    root.geometry("500x300")
    root.configure(bg="#222")
    
    tk.Label(root, text="서비스 종료되었습니다.", font=("Arial", 25, "bold"), fg="#ff4d4d", bg="#222").pack(pady=(60, 20))
    tk.Label(root, text="MPL Maker PY의 서비스가 종료되었습니다.\n이제 모든 기기에서 웹브라우저 클라우드를 통해\n더 빠르고 안정적으로 직접 제작하고 추출할 수 있습니다.\n단,베타서비스 중이므로 불안전 할 수 있습니다.\n이 프로그램으로 다운 받은 mpl 파일은 5주 내에 새로운 mpl 형식파일로 변경하십시오.", 
             font=("Malgun Gothic", 12), fg="white", bg="#222", justify="center").pack()
    
    tk.Button(root, text="사용 종료", command=root.destroy, bg="#007bff", fg="white", font=("Arial", 12, "bold"), width=20, pady=10).pack(pady=30)
    root.mainloop()

if __name__ == "__main__":
    show_deprecated()
