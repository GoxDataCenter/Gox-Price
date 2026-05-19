from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from openpyxl import load_workbook

SECRET = "change-me-in-production"
ALGO = "HS256"


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    admin = "admin"
    sales = "sales"


class SupplierLine(str, Enum):
    acronis = "acronis"
    fortinet = "fortinet"
    bare_metal = "bare_metal"
    colocation = "colocation"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(SAEnum(Role))


class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[SupplierLine] = mapped_column(SAEnum(SupplierLine), index=True)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("14.53"))
    markup_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("20"))
    hour_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("24"))


class PriceListVersion(Base):
    __tablename__ = "price_list_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[SupplierLine] = mapped_column(SAEnum(SupplierLine), index=True)
    supplier_name: Mapped[str] = mapped_column(String(120))
    uploaded_by: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active: Mapped[bool] = mapped_column(default=True)
    items: Mapped[List["PriceItem"]] = relationship(back_populates="version", cascade="all,delete")


class PriceItem(Base):
    __tablename__ = "price_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("price_list_versions.id"), index=True)
    sku: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    currency: Mapped[str] = mapped_column(String(10), default="BRL")
    type: Mapped[str] = mapped_column(String(30), default="default")
    version: Mapped[PriceListVersion] = relationship(back_populates="items")


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[SupplierLine] = mapped_column(SAEnum(SupplierLine), index=True)
    created_by: Mapped[str] = mapped_column(String(60))
    customer_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    payload: Mapped[str] = mapped_column(Text)
    total_monthly: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_contract: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


engine = create_engine("sqlite:////data/pricing.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

app = FastAPI(title="GOX Pricing Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    role: Role


class QuoteItemIn(BaseModel):
    sku: str
    quantity: float


class CalculateIn(BaseModel):
    line: SupplierLine
    customer_name: Optional[str] = None
    contract_months: int = 36
    analyst_hours: float = 0
    exchange_rate: float = 1
    items: List[QuoteItemIn]


class SettingUpdate(BaseModel):
    tax_percent: float
    markup_percent: float
    hour_cost: float


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def bootstrap(db: Session):
    if not db.query(User).count():
        db.add_all([
            User(username="admin", password="admin123", role=Role.admin),
            User(username="vendas", password="vendas123", role=Role.sales),
        ])
    for line in SupplierLine:
        exists = db.query(Setting).filter(Setting.line == line).first()
        if not exists:
            db.add(Setting(line=line))
    db.commit()


def create_token(username: str, role: Role):
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    return jwt.encode({"sub": username, "role": role.value, "exp": exp}, SECRET, algorithm=ALGO)


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(db_session)
):
    try:
        payload = jwt.decode(cred.credentials, SECRET, algorithms=[ALGO])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token inválido") from exc
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Apenas admin")
    return user


@app.on_event("startup")
def startup():
    with SessionLocal() as db:
        bootstrap(db)


@app.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(db_session)):
    user = db.query(User).filter(User.username == body.username, User.password == body.password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return TokenOut(access_token=create_token(user.username, user.role), role=user.role)


@app.get("/catalog/{line}")
def catalog(line: SupplierLine, q: str = "", db: Session = Depends(db_session), user: User = Depends(get_current_user)):
    active = db.query(PriceListVersion).filter(PriceListVersion.line == line, PriceListVersion.is_active.is_(True)).first()
    if not active:
        return []
    items = db.query(PriceItem).filter(PriceItem.version_id == active.id)
    if q:
        q_like = f"%{q}%"
        items = items.filter((PriceItem.sku.like(q_like)) | (PriceItem.description.like(q_like)))
    return [{"sku": i.sku, "description": i.description, "unit_cost": float(i.unit_cost), "currency": i.currency, "type": i.type} for i in items.limit(200).all()]


@app.get("/admin/settings/{line}")
def get_settings(line: SupplierLine, db: Session = Depends(db_session), user: User = Depends(get_current_user)):
    st = db.query(Setting).filter(Setting.line == line).first()
    if not st:
        raise HTTPException(status_code=404, detail="Linha sem configuração")
    return {"line": st.line.value, "tax_percent": float(st.tax_percent), "markup_percent": float(st.markup_percent), "hour_cost": float(st.hour_cost)}


@app.put("/admin/settings/{line}")
def update_settings(line: SupplierLine, body: SettingUpdate, db: Session = Depends(db_session), admin: User = Depends(require_admin)):
    st = db.query(Setting).filter(Setting.line == line).first()
    if not st:
        st = Setting(line=line)
        db.add(st)
    st.tax_percent = Decimal(str(body.tax_percent))
    st.markup_percent = Decimal(str(body.markup_percent))
    st.hour_cost = Decimal(str(body.hour_cost))
    db.commit()
    return {"ok": True}


@app.post("/admin/import-price-list")
def import_price_list(
    line: SupplierLine = Form(...),
    supplier_name: str = Form(...),
    sku_column: str = Form("part"),
    desc_column: str = Form("desc"),
    cost_column: str = Form("price"),
    currency: str = Form("BRL"),
    type_column: str = Form("type"),
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    admin: User = Depends(require_admin),
):
    wb = load_workbook(file.file, data_only=True)
    ws = wb.active
    headers = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    idx = {h.lower(): i for i, h in enumerate(headers)}

    for required in [sku_column.lower(), desc_column.lower(), cost_column.lower()]:
        if required not in idx:
            raise HTTPException(status_code=400, detail=f"Coluna obrigatória não encontrada: {required}")

    db.query(PriceListVersion).filter(PriceListVersion.line == line, PriceListVersion.is_active.is_(True)).update({"is_active": False})

    version = PriceListVersion(line=line, supplier_name=supplier_name, uploaded_by=admin.username, is_active=True)
    db.add(version)
    db.flush()

    imported = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        sku_val = row[idx[sku_column.lower()]] if idx[sku_column.lower()] < len(row) else None
        desc_val = row[idx[desc_column.lower()]] if idx[desc_column.lower()] < len(row) else ""
        cost_val = row[idx[cost_column.lower()]] if idx[cost_column.lower()] < len(row) else None
        type_val = row[idx[type_column.lower()]] if type_column.lower() in idx and idx[type_column.lower()] < len(row) else "default"

        if sku_val in (None, "") or cost_val in (None, ""):
            continue
        try:
            cost = Decimal(str(cost_val).replace(",", "."))
        except Exception:
            continue

        db.add(
            PriceItem(
                version_id=version.id,
                sku=str(sku_val).strip(),
                description=str(desc_val or "").strip(),
                unit_cost=cost,
                currency=currency.upper(),
                type=str(type_val or "default").strip(),
            )
        )
        imported += 1

    db.commit()
    return {"ok": True, "version_id": version.id, "imported": imported}


@app.post("/pricing/calculate")
def calculate(body: CalculateIn, db: Session = Depends(db_session), user: User = Depends(get_current_user)):
    active = db.query(PriceListVersion).filter(PriceListVersion.line == body.line, PriceListVersion.is_active.is_(True)).first()
    if not active:
        raise HTTPException(status_code=400, detail="Sem price list ativa para a linha")
    st = db.query(Setting).filter(Setting.line == body.line).first()

    subtotal = Decimal("0")
    breakdown = []
    for req_item in body.items:
        item = db.query(PriceItem).filter(PriceItem.version_id == active.id, PriceItem.sku == req_item.sku).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"SKU não encontrado: {req_item.sku}")
        line_total = Decimal(str(req_item.quantity)) * item.unit_cost * Decimal(str(body.exchange_rate))
        subtotal += line_total
        breakdown.append({"sku": item.sku, "description": item.description, "quantity": req_item.quantity, "unit_cost": float(item.unit_cost), "line_total": float(line_total)})

    service_cost = Decimal(str(body.analyst_hours)) * st.hour_cost
    base = subtotal + service_cost
    taxed = base * (Decimal("1") + (st.tax_percent / Decimal("100")))
    monthly = taxed * (Decimal("1") + (st.markup_percent / Decimal("100")))
    total_contract = monthly * Decimal(str(body.contract_months))

    q = Quote(
        line=body.line,
        created_by=user.username,
        customer_name=body.customer_name,
        payload=str(breakdown),
        total_monthly=monthly.quantize(Decimal("0.01")),
        total_contract=total_contract.quantize(Decimal("0.01")),
    )
    db.add(q)
    db.commit()

    return {
        "quote_id": q.id,
        "line": body.line.value,
        "base_cost": float(base),
        "monthly_price": float(q.total_monthly),
        "contract_total": float(q.total_contract),
        "tax_percent": float(st.tax_percent),
        "markup_percent": float(st.markup_percent),
        "breakdown": breakdown,
    }


@app.get("/integrations/ixc/quote/{quote_id}")
def quote_for_ixc(quote_id: int, db: Session = Depends(db_session), user: User = Depends(get_current_user)):
    q = db.query(Quote).filter(Quote.id == quote_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotação não encontrada")
    return {
        "solution": q.line.value,
        "quote_id": q.id,
        "customer_name": q.customer_name,
        "monthly_price": float(q.total_monthly),
        "contract_total": float(q.total_contract),
        "created_at": q.created_at.isoformat(),
    }


@app.get("/health")
def health():
    return {"ok": True}
