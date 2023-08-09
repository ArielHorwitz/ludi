# Ludi

A homemade variation of the classic multiplayer game of Ludo, built on top of [Mousefox](https://github.com/ArielHorwitz/mousefox).

![Preview Image](/preview.png)

### Controls
- Roll / confirm: `spacebar`
- Select unit / dice: `1`, `2`, ..., `F1`, `F2`, ...
- Cancel: `escape`

### Features
- Simple controls
- Bots / Multiplayer (WAN with port forwarding)
- Configurable gameplay settings (board size, dice count, etc.)
- [pgnet](https://github.com/ArielHorwitz/pgnet/) features (E2E encryption, multiple games per server, etc.)

### Install From Source
It is recommended to use a [virtual environment](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/) when installing packages:
```console
git clone https://github.com/ArielHorwitz/ludi.git
cd ludi
pip install -r requirements.txt
python src/main.py
```

