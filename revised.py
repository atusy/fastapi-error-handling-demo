from http import HTTPStatus
from logging import getLogger

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware import base

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


@app.middleware("http")
async def server_error_middleware(
    request: Request, call_next: base.RequestResponseEndpoint
) -> Response:
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Unexpected Error!!!",
            exc_info=False,  # エラー追跡には `True` を指定するべきだが、デモでは非表示
        )
        return JSONResponse(
            status_code=500, content={"message": "Internal Server Error"}
        )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
