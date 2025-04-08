# FastAPIのエラーハンドリングの基本と、ハンドリング漏れ対策

- `index.Rmd`/`index.md`: 解説
- `main.py`: FastAPIのサンプルコード（全エラーのハンドリングを例外ハンドラで実施）
- `revised.py`: `main.py`を改修し`Exception`のハンドリングをミドルウェアで実施するサンプルコード
