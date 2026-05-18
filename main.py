from __future__ import annotations

import tkinter as tk

from gui import QQSenderApp


def main() -> None:
    root = tk.Tk()
    QQSenderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
