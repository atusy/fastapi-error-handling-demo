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
