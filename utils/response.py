from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

def success_response(
        message: str,
        data = None
):
    content = {
        "code": 200,
        "message": message,
        "data": data
    }
    return JSONResponse(jsonable_encoder(content))