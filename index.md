APIサーバーの実装では、プログラムエラーをハンドリングして、クライアントエラーやサーバーエラーを適切にレスポンスすることが求められます。 同時に、エラーに関するログを出力することも重要です。

PythonのWebフレームワークである[FastAPI](https://fastapi.tiangolo.com/ja/)にも、このような需要エラーハンドリングの仕組みが用意されています。 基本的には公式ドキュメントに従って、例外ハンドラを追加すればいいのですが、ハンドリング漏れした`Exception`のログを残すような用途に例外ハンドラは不適です。

そこで、この記事では以下の3点について紹介します。

- FastAPIのエラーハンドリングの基本
- 例外ハンドラが`Exception`のハンドリングに不適な理由
- `Exception`をハンドリングするためのミドルウェアの実装方法

なお、本記事で利用したコードはGitHubのリポジトリに公開しています。

<https://github.com/atusy/fastapi-error-handling-demo>

## カスタム例外ハンドラによる一般的な例外のハンドリング

基本的な方法について、詳しくは日本語の公式ドキュメントを参照してください。 ここでは簡単に紹介します。

> FastAPI \> 学習 \> チュートリアル - ユーザーガイド \> エラーハンドリング  
> <https://fastapi.tiangolo.com/ja/tutorial/handling-errors/>

ドキュメントでは例外の扱いかたとして、主に2つの方法を説明しています。

- HTTPレスポンスをエラーでクライアントに返すには、`raise HTTPException(...)`する
- 特定のエラーを所定のHTTPレスポンスに自動変換するには、`@app.exception_handler(...)`でカスタム例外ハンドラを追加する
  - `HTTPException`についても、FastAPIが組込みの例外ハンドラを使ってHTTPレスポンスに変換しているので、エラーハンドリングの本質は例外ハンドラと言えます（筆者補足）

カスタム例外ハンドラは、FastAPIに組込みのハンドラを上書きして独自のレスポンスに統一したい場合や（[デフォルトの例外ハンドラのオーバーライド](https://fastapi.tiangolo.com/ja/tutorial/handling-errors/#_6)）、依存パッケージ由来の例外をハンドリングしたい場合に便利です。 後者の例として、Google Cloud SDKでService Unavailableが発生した場合に、エラーログとともに503 Service Unavailableを返すような実装が考えられます。

``` python
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPIError, ServiceUnavailable

@app.exception_handler(GoogleAPIError)
async def handle_http_exception(__: Request, exc: GoogleAPIError) -> Response:
    if isinstance(exc, ServiceUnavailable):
        logger.exception("Google Cloud is Service Unavailable")
        return JSONResponse(
            content={"message": "Service Unavailable"},
            status_code=503,
        )
    raise exc # 未処理のエラーをraiseしておくとFastAPIが500にしてくれる
```

カスタム例外ハンドラでハンドリングしたエラーは例外が抑制されます。

ただし、基底クラスの`Exception`だけは例外で、未知のエラーを例外ハンドラーによってInternal Server Errorとしてサーバーエラーレスポンスに変換してもなお、例外が発生します。 プログラム自体は継続するものの、生のトレースバックがログに出力されます。 サーバーエラーのログを自前で出力している場合は、エラーログが2重になって冗長になります。 特に構造化ログを採用している場合に構造化されていないエラーログが混ざるので更に不便です。

例外ハンドラの結果を無視して例外を`raise`する挙動はFastAPIが依存するStarleeteの仕様です。 `starlette.middleware.errors.ServerErrorMiddleware`のソースコードにその意図が記述されています。

>     # We always continue to raise the exception.
>     # This allows servers to log the error, or allows test clients
>     # to optionally raise the error within the test case.
>
> <https://github.com/encode/starlette/blob/c8a46925366361e40b65b117473db1342895b904/starlette/middleware/errors.py?plain=1#L184-L186>

実際に、`Exception`を例外ハンドラで扱った場合のログがどうなるか、試してみましょう。 検証に使ったソースコードは以下にあります。 FastAPIが依存しているStarletteのバージョンについては0.45.3で固定しています。 記事執筆の2025-04-07時点で最新の0.46.1にすると、バグの関係で今回紹介するコードで別の例外が発生するのでご注意ください。

<https://github.com/atusy/fastapi-error-handling-demo>

たとえば、以下のコードでは、`HTTPException`と`Exception`のハンドラーを設定しています。 `GET /404`すると、`HTTPException`が発生し、`GET /500`すると、`Exception`が発生しますが、ハンドラがあるので、どちらもエラーが抑制されると期待したいところです。 ところが実際には`GET /500`でエラーが発生していることをサーバーログから確認できます。

``` python
from http import HTTPStatus
from logging import getLogger

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

logger = getLogger("uvicorn")
app = FastAPI()


@app.get("/404")
async def raise404(__: Request):
    raise HTTPException(status_code=404, detail="Not Found")


@app.get("/500")
async def raise500(__: Request):
    raise Exception("Unexpected Error!!")


@app.exception_handler(HTTPException)
async def handle_http_exception(__: Request, exc: HTTPException):
    return JSONResponse(
        content={"message": HTTPStatus(exc.status_code).phrase},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def handle_exception(__: Request, exc: Exception) -> Response:
    logger.exception(
        str(exc),
        exc_info=False,  # エラー追跡には `True` を指定するべきだが、デモでは非表示
    )
    return JSONResponse(
        content={"message": "Internal Server Error"},
        status_code=500,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

<details>
<summary>
`GET /404`と`GET /500`した時のサーバーログ
</summary>

    INFO:     Started server process [1595802]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     127.0.0.1:47962 - "GET /404 HTTP/1.1" 404 Not Found
    ERROR:    Unexpected Error!!
    INFO:     127.0.0.1:47974 - "GET /500 HTTP/1.1" 500 Internal Server Error
    ERROR:    Exception in ASGI application
    Traceback (most recent call last):
      File ".../demo/.venv/
    lib/python3.12/site-packages/uvicorn/protocols/http/h11_impl.py", line 403, in run_asgi
        result = await app(  # type: ignore[func-returns-value]
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File ".../demo/.venv/
    lib/python3.12/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
        return await self.app(scope, receive, send)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File ".../demo/.venv/
    lib/python3.12/site-packages/fastapi/applications.py", line 1054, in __call__
        await super().__call__(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/applications.py", line 112, in __call__
        await self.middleware_stack(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/middleware/errors.py", line 187, in __call__
        raise exc
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/middleware/errors.py", line 165, in __call__
        await self.app(scope, receive, _send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
        await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
        raise exc
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
        await app(scope, receive, sender)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/routing.py", line 715, in __call__
        await self.middleware_stack(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/routing.py", line 735, in app
        await route.handle(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/routing.py", line 288, in handle
        await self.app(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/routing.py", line 76, in app
        await wrap_app_handling_exceptions(app, request)(scope, receive, send)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
        raise exc
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
        await app(scope, receive, sender)
      File ".../demo/.venv/
    lib/python3.12/site-packages/starlette/routing.py", line 73, in app
        response = await f(request)
                   ^^^^^^^^^^^^^^^^
      File ".../demo/.venv/
    lib/python3.12/site-packages/fastapi/routing.py", line 301, in app
        raw_response = await run_endpoint_function(
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File ".../demo/.venv/
    lib/python3.12/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
        return await dependant.call(**values)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File ".../demo/main.p
    y", line 19, in raise500
        raise Exception("Unexpected Error!!")
    Exception: Unexpected Error!!
    INFO:     Shutting down
    INFO:     Waiting for application shutdown.
    INFO:     Application shutdown complete.
    INFO:     Finished server process [1595802]

</details>

## ミドルウェアによる`Exception`のハンドリング

カスタム例外ハンドラで`Exception`を処理すると、ログの観点で都合が悪いことを確認しました。 これがFastAPIおよびStarletteの仕様である以上、`Exception`に関しては`＠app.exception_handler(Exception)`でハンドリングせず、`ServerErrorMiddleware`の代替となるミドルウェアを実装するとよさそうです。 Internal Server Errorを発生させている状況はエラーハンドリングできていないと見做せば、`@app.exception_handler(Exception)`せずに、このようなミドルウェアを実装することは妥当そうに思えます。

そこで、プログラムに以下のような修正を加えます。

``` bash
diff -u main.py revised.py
```

``` diff
--- main.py 2025-04-07 13:32:10
+++ revised.py  2025-04-07 13:32:10
@@ -4,6 +4,7 @@
 import uvicorn
 from fastapi import FastAPI, HTTPException, Request, Response
 from fastapi.responses import JSONResponse
+from starlette.middleware import base
 
 logger = getLogger("uvicorn")
 app = FastAPI()
@@ -27,16 +28,20 @@
     )
 
 
-@app.exception_handler(Exception)
-async def handle_exception(__: Request, exc: Exception) -> Response:
-    logger.exception(
-        str(exc),
-        exc_info=False,  # エラー追跡には `True` を指定するべきだが、デモでは非表示
-    )
-    return JSONResponse(
-        content={"message": "Internal Server Error"},
-        status_code=500,
-    )
+@app.middleware("http")
+async def server_error_middleware(
+    request: Request, call_next: base.RequestResponseEndpoint
+) -> Response:
+    try:
+        return await call_next(request)
+    except Exception:
+        logger.exception(
+            "Unexpected Error!!!",
+            exc_info=False,  # エラー追跡には `True` を指定するべきだが、デモでは非表示
+        )
+        return JSONResponse(
+            status_code=500, content={"message": "Internal Server Error"}
+        )
 
 
 if __name__ == "__main__":
```

この状態で`GET /404`と`GET /500`した時のサーバーログを見てみると、Internal Server Error発生時のトレースバックが消滅し、エラーログが開発者側で`logger.exception(...)`を使って出したものだけになりました。

    INFO:     Started server process [1595222]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     127.0.0.1:36242 - "GET /404 HTTP/1.1" 404 Not Found
    ERROR:    Unexpected Error!!!
    INFO:     127.0.0.1:36258 - "GET /500 HTTP/1.1" 500 Internal Server Error
    INFO:     Shutting down
    INFO:     Waiting for application shutdown.
    INFO:     Application shutdown complete.
    INFO:     Finished server process [1595222]

## おわりに

FastAPIのカスタム例外ハンドラは、依存パッケージなどに由来する既知の例外の処理に便利ですが、処理基底クラスのExceptionをハンドリングしてログを残す場合はミドルウェアを実装する必要があることを確認しました。 また、その理由がFastAPIが依存しているStarletteの仕様であることも確認しました。 FastAPIの実装はStarletteに強く依存しているので、なにか問題があるときは、FastAPIに限らずStarletteのソースコードを確認することが重要そうです。
