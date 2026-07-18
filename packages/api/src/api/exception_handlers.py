from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from api.exceptions import GolfcartError, GolfcartRequestValidationError


async def golfcart_error_handler(request: Request, exc: Exception) -> JSONResponse:
  if not isinstance(exc, GolfcartError):
    raise TypeError(f"Expected GolfcartError, got {type(exc).__name__}")

  content: dict = {"error": type(exc).__name__, "detail": exc.message}
  if isinstance(exc, GolfcartRequestValidationError):
    content["errors"] = jsonable_encoder(exc.errors())

  return JSONResponse(
    status_code=exc.status_code,
    content=content,
    headers=exc.headers,
  )


def add_exception_handlers(app: FastAPI) -> None:
  app.add_exception_handler(GolfcartError, golfcart_error_handler)
