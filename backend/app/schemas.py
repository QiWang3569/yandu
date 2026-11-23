from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

CATEGORIES = ['课程资料与书籍', '数码与影音', '校园出行与运动', '宿舍生活与家电', '美妆服饰与周边', '人员招募']
CAMPUSES = ['燕园校本部', '万柳学区', '医学部', '昌平新校区', '不限校区']
CONDITIONS = ['全新', '95新', '9成新', '8成新', '基本可用']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ItemCreate(StrictModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=3000)
    category: str
    price: Decimal = Field(ge=0, le=999999, max_digits=8, decimal_places=2)
    campus: str
    condition_grade: str = '95新'
    tags: list[str] = Field(default_factory=list, max_length=8)
    images: list[str] = Field(default_factory=list, max_length=9)

    @field_validator('images')
    @classmethod
    def images_valid(cls, v):
        if len(v) != len(set(v)):
            raise ValueError('不能重复添加同一张图片')
        return v

    @field_validator('category')
    @classmethod
    def category_valid(cls, v):
        if v not in CATEGORIES:
            raise ValueError('请选择有效的商品分类')
        return v

    @field_validator('campus')
    @classmethod
    def campus_valid(cls, v):
        if v not in CAMPUSES:
            raise ValueError('请选择有效的校区')
        return v

    @field_validator('condition_grade')
    @classmethod
    def condition_valid(cls, v):
        if v not in CONDITIONS:
            raise ValueError('请选择有效的成色')
        return v

    @field_validator('tags')
    @classmethod
    def tags_valid(cls, v):
        if any(not t.strip() or len(t) > 30 for t in v):
            raise ValueError('标签长度为 1–30 字')
        return list(dict.fromkeys(t.strip() for t in v))


class QueryIn(StrictModel):
    raw_query: str = Field(min_length=2, max_length=2500)


class ParsedIntent(StrictModel):
    category: str | None = None
    max_price: Decimal | None = Field(default=None, ge=0, le=999999, decimal_places=2)
    campus: str = '不限校区'
    keywords: list[str] = Field(default_factory=list, max_length=12)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=12)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    condition_grade: str | None = None
    clarification: str | None = Field(default=None, max_length=500)
    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v)))
    condition_valid = field_validator('condition_grade')(classmethod(lambda cls, v: ItemCreate.condition_valid(v) if v else None))
    tags_valid = field_validator('keywords')(classmethod(lambda cls, v: ItemCreate.tags_valid(v)))
    exclusions_valid = field_validator('excluded_keywords')(classmethod(lambda cls, v: ItemCreate.tags_valid(v)))
    preferences_valid = field_validator('preferences')(classmethod(lambda cls, v: ItemCreate.tags_valid(v)))

    @model_validator(mode='after')
    def consistent_conditions(self):
        if set(self.excluded_keywords) & (set(self.keywords) | set(self.preferences)):
            raise ValueError('同一特征不能同时要求与排除，请调整条件')
        return self


class IntentCondition(StrictModel):
    role: Literal['required', 'preferred', 'excluded']
    term: str = Field(min_length=1, max_length=30)
    quote: str = Field(default='', max_length=40)


class StructuredIntent(StrictModel):
    """Internal extraction shape; flattened to ParsedIntent before it leaves the service."""
    category: str | None = None
    max_price: Decimal | None = None
    budget_quote: str = Field(default='', max_length=40)
    campus: str = '不限校区'
    campus_quote: str = Field(default='', max_length=40)
    condition_grade: str | None = None
    condition_quote: str = Field(default='', max_length=40)
    conditions: list[IntentCondition] = Field(default_factory=list, max_length=24)
    clarification: str | None = Field(default=None, max_length=500)
    clarification_quotes: list[str] = Field(default_factory=list, max_length=8)


class IntentCreate(QueryIn):
    parsed: ParsedIntent


class SmartSearchIn(StrictModel):
    query: str = Field(min_length=2, max_length=500)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=12, ge=1, le=50)
    sort: Literal['recommended', 'newest', 'price_asc', 'price_desc'] = 'recommended'


class StatusChange(StrictModel):
    status: Literal['ACTIVE', 'RESERVED', 'SOLD']


class IntentChange(StrictModel):
    action: Literal['pause', 'resume', 'renew']


class WantedCreate(StrictModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=2500)
    category: str | None = None
    budget: Decimal | None = Field(default=None, ge=0, le=999999, decimal_places=2)
    campus: str = '不限校区'
    intent_id: str | None = None
    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v)))

    @model_validator(mode='after')
    def query_length(self):
        query = self.description if self.description.startswith(self.title) else self.title + '\n' + self.description
        if len(query) > 2500:
            raise ValueError('求购标题与描述合计不能超过 2500 字')
        return self


class ItemUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=5, max_length=3000)
    category: str | None = None
    price: Decimal | None = Field(default=None, ge=0, le=999999, max_digits=8, decimal_places=2)
    campus: str | None = None
    condition_grade: str | None = None
    tags: list[str] | None = Field(default=None, max_length=8)
    images: list[str] | None = Field(default=None, max_length=9)
    images_valid = field_validator('images')(classmethod(lambda cls, v: ItemCreate.images_valid(v) if v is not None else None))

    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v) if v is not None else None))
    condition_valid = field_validator('condition_grade')(classmethod(lambda cls, v: ItemCreate.condition_valid(v) if v is not None else None))
    tags_valid = field_validator('tags')(classmethod(lambda cls, v: ItemCreate.tags_valid(v) if v is not None else None))


class WantedUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2500)
    category: str | None = None
    budget: Decimal | None = Field(default=None, ge=0, le=999999, decimal_places=2)
    campus: str | None = None

    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v) if v is not None else None))


class WantedParseRequest(StrictModel):
    raw: str = Field(min_length=2, max_length=2500)


class ParsedWanted(StrictModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2500)
    category: str | None = None
    budget: Decimal | None = Field(default=None, ge=0, le=999999, decimal_places=2)
    campus: str = '不限校区'
    clarification: str | None = Field(default=None, max_length=500)

    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v)))


class ReportCreate(StrictModel):
    reason: str = Field(min_length=5, max_length=1000)


class ReviewAction(StrictModel):
    action: Literal['hide', 'restore', 'dismiss']
    note: str = Field(min_length=5, max_length=500)
    confirmed: Literal[True]


class DemoLogin(StrictModel):
    profile: Literal['buyer', 'seller', 'admin']


class EmailCodeRequest(StrictModel):
    email: str = Field(max_length=254)


class EmailCodeVerify(EmailCodeRequest):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    code: str = Field(pattern=r'^\d{8}$')
    nickname: str = Field(default='', max_length=50)
    # Accepted for older clients; new accounts are created without a campus.
    campus: str = '不限校区'
    password: SecretStr | None = None
    intent: Literal['register', 'login', 'auto'] = 'auto'

    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v)))


class PasswordLogin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=254)
    password: SecretStr


class PasswordSet(PasswordLogin):
    code: str = Field(pattern=r'^\d{8}$')


class ProfileUpdate(StrictModel):
    email_notifications: bool | None = Field(default=None, strict=True)
    nickname: str | None = Field(default=None, min_length=2, max_length=50)
    campus: str | None = None
    bio: str | None = Field(default=None, max_length=160)
    avatar_color: Literal['sage', 'blue', 'peach', 'lavender'] | None = None

    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v)))


class ChatMessageCreate(StrictModel):
    body: str = Field(default='', max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.body and not self.images:
            raise ValueError('消息不能为空')
        if len(set(self.images)) != len(self.images):
            raise ValueError('不能重复添加同一张图片')
        return self


class ChatReportCreate(StrictModel):
    reason: str = Field(min_length=5, max_length=1000)


class ChatReviewAction(StrictModel):
    action: Literal['hide', 'dismiss']
    note: str = Field(min_length=5, max_length=500)
    confirmed: Literal[True]


class DealAction(StrictModel):
    action: Literal['request', 'reserve', 'decline', 'cancel', 'sold', 'confirm']


class IntentComplete(StrictModel):
    item_id: str | None = None


class AnnouncementCreate(StrictModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=5, max_length=5000)
    kind: Literal['公告', '更新'] = '公告'


class AnnouncementUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    body: str | None = Field(default=None, min_length=5, max_length=5000)
    kind: Literal['公告', '更新'] | None = None
    active: bool | None = None


class AnnouncementReadRequest(StrictModel):
    ids: list[str] = Field(min_length=1, max_length=50)


class ItemParseRequest(StrictModel):
    raw: str = Field(min_length=5, max_length=3000)


class ItemDraftImport(StrictModel):
    text: str = Field(min_length=5, max_length=10000)


class ItemDraftUpdate(StrictModel):
    raw: str | None = Field(default=None, min_length=5, max_length=3000)
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=5, max_length=3000)
    category: str | None = None
    price: Decimal | None = Field(default=None, ge=0, le=999999, max_digits=8, decimal_places=2)
    campus: str | None = None
    condition_grade: str | None = None
    tags: list[str] | None = Field(default=None, max_length=8)
    images: list[str] | None = Field(default=None, max_length=9)
    images_valid = field_validator('images')(classmethod(lambda cls, v: ItemCreate.images_valid(v) if v is not None else None))

    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v) if v is not None else None))
    condition_valid = field_validator('condition_grade')(classmethod(lambda cls, v: ItemCreate.condition_valid(v) if v is not None else None))
    tags_valid = field_validator('tags')(classmethod(lambda cls, v: ItemCreate.tags_valid(v) if v is not None else None))


class ParsedItem(StrictModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=3000)
    category: str | None = None
    price: Decimal | None = Field(default=None, ge=0, le=999999, decimal_places=2)
    campus: str = '燕园校本部'
    condition_grade: str = '95新'
    tags: list[str] = Field(default_factory=list, max_length=8)
    clarification: str | None = Field(default=None, max_length=500)

    category_valid = field_validator('category')(classmethod(lambda cls, v: ItemCreate.category_valid(v) if v is not None else None))
    campus_valid = field_validator('campus')(classmethod(lambda cls, v: ItemCreate.campus_valid(v)))
    condition_valid = field_validator('condition_grade')(classmethod(lambda cls, v: ItemCreate.condition_valid(v) if v else None))
    tags_valid = field_validator('tags')(classmethod(lambda cls, v: ItemCreate.tags_valid(v)))


class DwellReport(StrictModel):
    page: str = Field(min_length=1, max_length=64)
    item_id: str | None = None
    duration_seconds: int = Field(ge=1, le=86400)
