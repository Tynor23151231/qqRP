from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ButtonFlow


class ButtonFlowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_flows(self, owner_id: int) -> list[ButtonFlow]:
        result = await self.session.execute(
            select(ButtonFlow).where(ButtonFlow.owner_id == owner_id).order_by(ButtonFlow.id)
        )
        return list(result.scalars().all())

    async def get_by_trigger(self, owner_id: int, trigger: str) -> ButtonFlow | None:
        result = await self.session.execute(
            select(ButtonFlow).where(
                ButtonFlow.owner_id == owner_id, ButtonFlow.trigger == trigger.lower()
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, flow_id: int) -> ButtonFlow | None:
        return await self.session.get(ButtonFlow, flow_id)

    async def create(self, owner_id: int, trigger: str, screens: list[dict]) -> ButtonFlow:
        flow = ButtonFlow(owner_id=owner_id, trigger=trigger.lower(), screens=screens)
        self.session.add(flow)
        await self.session.commit()
        await self.session.refresh(flow)
        return flow

    async def create_or_replace(self, owner_id: int, trigger: str, screens: list[dict]) -> ButtonFlow:
        """Пересоздаёт цепочку с тем же названием (используется при "Изменить" и при импорте по ссылке)."""
        existing = await self.get_by_trigger(owner_id, trigger)
        if existing is not None:
            await self.session.delete(existing)
            await self.session.flush()
        return await self.create(owner_id, trigger, screens)

    async def delete(self, owner_id: int, trigger: str) -> bool:
        flow = await self.get_by_trigger(owner_id, trigger)
        if flow is None:
            return False
        await self.session.delete(flow)
        await self.session.commit()
        return True
