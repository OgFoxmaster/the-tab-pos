from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/mpesa", tags=["mpesa"])


def _payment_not_configured() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="M-Pesa checkout is disabled until payment callbacks can be verified.",
    )


@router.post("/stk_push")
async def initiate_stk_push():
    _payment_not_configured()


@router.post("/callback")
async def mpesa_callback():
    _payment_not_configured()


@router.post("/timeout")
async def mpesa_timeout():
    _payment_not_configured()
