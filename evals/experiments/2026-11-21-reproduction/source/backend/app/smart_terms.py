"""Lexical product identity and attribute evidence for interactive marketplace search."""
from dataclasses import dataclass
from functools import lru_cache
import re
import unicodedata

from .schemas import CAMPUSES, CONDITIONS

# Equivalents preserve specificity. Brands, technologies and subtypes are
# handled directionally in evidence(), never rewritten to their parent in a query.
ALIASES = {
    '滑鼠': '鼠标', 'mouse': '鼠标', 'keyboard': '键盘', 'monitor': '显示器',
    '屏幕': '显示器', '单车': '自行车', '山地车': '山地自行车', '鞋子': '鞋',
    '无声': '静音', '阅读灯': '台灯', '课本': '教材', '高数': '高等数学',
    'tennis racket': '网球拍', 'tennis racquet': '网球拍', 'badminton racket': '羽毛球拍',
    'badminton racquet': '羽毛球拍', '耳麦': '耳机', '九五新': '95新',
    '九成新': '9成新', '八成新': '8成新',
}
# A noun at the end of a product phrase determines what is being sold:
# "键盘接收器" sells a receiver; "键盘，附接收器" sells a keyboard.
ACCESSORIES = ('适配器', '充电器', '接收器', '支架', '保护壳', '保护套', '鼠标垫', '键帽',
               '键盘膜', '耳机套', '手机壳', '充电线', '数据线')
NOUNS = ('电脑','笔记本','鼠标','键盘','耳机','平板','显示器','路由器','自行车',
         '网球拍','羽毛球拍','球拍','鞋','包','台灯','风扇','床垫','电饭煲','冰箱',
         '相机','手环','手柄','扩展坞','数据线','接收器','充电器','适配器','支架',
         '教材','词典','手机','车锁','外套')
# Search from specific to general; a buyer asking for a subtype keeps that constraint.
SUBTYPES = {'电脑': ('笔记本','macbook'), '鼠标': ('mx master',), '耳机': ('airpods',),
            '平板': ('ipad',), '无线': ('蓝牙',), '球拍': ('网球拍','羽毛球拍')}
NOUN_PATTERN = re.compile('|'.join(sorted(set(NOUNS + ACCESSORIES), key=lambda w: (-len(w), w))))
OFFERS_END = re.compile(r'[，,。；;]|不含|不带|不附|附赠|附带|赠送|附|送(?!(?:货|达))')
COMPATIBILITY = re.compile(r'适用于|适配(?!器)|兼容')
DEVICE_FAMILY = {'macbook': '电脑', 'ipad': '平板', 'airpods': '耳机', 'mx master': '鼠标'}
NEGATIVE = re.compile(r'(?:并非|不是|不属于|不支持|不具备|不包含|不含|不带|不配|没有|不提供|不出售|非|无|不)\s*$')
ALIAS_PATTERN = re.compile('|'.join(re.escape(k) for k in sorted(ALIASES, key=len, reverse=True)))
INCLUSION = {('带',), ('含',), ('配',), ('附带',)}


def normalized(text):
    text = unicodedata.normalize('NFKC', text).lower().strip()
    return ALIAS_PATTERN.sub(lambda m: ALIASES[m.group()], text)


def affirmed(text, word):
    for term in (word, *SUBTYPES.get(word, ())):
        for match in re.finditer(re.escape(term), text):
            if not NEGATIVE.search(text[:match.start()]):
                return True
    return False


@dataclass(frozen=True)
class Listing:
    head: str
    subject_title: str
    fields: tuple[str, ...]
    price_cents: int
    condition_grade: str
    campus: str | None = None

    @classmethod
    def from_item(cls, item):
        title = normalized(item.title)
        primary = OFFERS_END.split(title, maxsplit=1)[0] or title
        # A compatibility note following a product name identifies the host device.
        # In a leading note (适用于手机的支架), the product name follows the note.
        if marker := COMPATIBILITY.search(primary):
            prefix, note = primary[:marker.start()].strip(), primary[marker.end():]
            if prefix:
                primary = prefix
            elif '的' in note:
                primary = note.split('的', 1)[1]
        primary = re.sub(r'[(][^()]*[)]', '', primary) or primary
        nouns = list(NOUN_PATTERN.finditer(primary))
        # Keep the full title as identity evidence when no known noun is present.
        head = nouns[-1].group() if nouns else ''
        fields = (title, normalized(item.description), *(normalized(tag) for tag in item.tags or ()))
        return cls(head, primary, fields, item.price_cents, item.condition_grade, getattr(item, 'campus', None))

    def evidence(self, word, *, minimum_condition=False):
        for campus in CAMPUSES[:-1]:
            if word in (campus, campus[:2]):
                return self.campus == campus
        if word == '免费':
            return self.price_cents == 0
        if word in CONDITIONS:
            if minimum_condition:
                return CONDITIONS.index(self.condition_grade) <= CONDITIONS.index(word)
            return self.condition_grade == word
        return any(affirmed(field, word) for field in self.fields)


@lru_cache(maxsize=2048)
def phrase_parts(text):
    text = normalized(text)
    matches = list(NOUN_PATTERN.finditer(text))
    if not matches:
        for brand, family in DEVICE_FAMILY.items():
            if text.startswith(brand):
                return family, (text,)
        return '', (text,) if text else ()
    noun = matches[-1]
    qualifiers = [part.strip() for part in (text[:noun.start()], text[noun.end():]) if part.strip()]
    return noun.group(), tuple(qualifiers)


def phrase_matches(listing, text, *, require_subject=True, minimum_condition=False):
    noun, qualifiers = phrase_parts(text)
    if noun and not require_subject and qualifiers in INCLUSION:
        qualifiers = ()
    if noun:
        if require_subject:
            if listing.head:
                if listing.head not in (noun, *SUBTYPES.get(noun, ())):
                    return False
            elif not affirmed(listing.subject_title, noun):
                return False
        elif not listing.evidence(noun):
            return False
    return bool(noun or qualifiers) and all(
        listing.evidence(word, minimum_condition=minimum_condition) for word in qualifiers
    )


HOST_ACCESSORY = re.compile(
    r'(?:usb[- ]?)?(macbook(?: air| pro)?|笔记本(?:电脑)?|手机|键盘|鼠标|平板|网球拍|羽毛球拍|球拍)'
    r'\s*(?:专用|用|的)?(' + '|'.join(ACCESSORIES) + ')', re.I)
MODEL_TERM = re.compile(r'macbook(?: air| pro)?|ipad(?: air| pro| mini)?|airpods(?: pro)?|mx master(?: \d\w*)?|笔记本电脑', re.I)
ATTRIBUTES = ('静音', '蓝牙', '有线', '无线', '降噪', '游戏', '人体工学',
              '机械', '黑色', '白色', '红色', '蓝色', '绿色', '粉色', '山地', '车锁', 'led')
NEGATED_PRODUCT = re.compile(
    r'(非|不支持|不带|不含|没有|不)(' + '|'.join(ATTRIBUTES) + r')的?(' + NOUN_PATTERN.pattern + r')',
    re.I,
)


def split_negated_products(text, excluded):
    def keep_subject(match):
        marker, feature, noun = match.groups()
        excluded.append(feature + noun if marker == '非' else feature)
        return noun
    return NEGATED_PRODUCT.sub(keep_subject, text)


def local_product_terms(text, keywords):
    """Keep explicit model, accessory and feature evidence in the positive query clause."""
    text = normalized(text)
    for match in HOST_ACCESSORY.finditer(text):
        host, accessory = match.groups()
        family = phrase_parts(host)[0] or host
        replaced = {host, family, accessory}
        if '笔记本' in host:
            replaced.add('电脑')
        keywords = [word for word in keywords if word not in replaced]
        prefix = text[match.start():match.start(1)].strip()
        keywords.append(prefix + host + accessory)
    remaining = HOST_ACCESSORY.sub(' ', text)
    for match in MODEL_TERM.finditer(remaining):
        model = match.group()
        family = phrase_parts(model)[0]
        if family and family not in remaining.replace(model, ''):
            keywords = [word for word in keywords if word != family]
        keywords.append(model)
    features = [word for word in ATTRIBUTES if word in remaining]
    if '蓝牙' in features and '无线' not in remaining:
        keywords = [word for word in keywords if word != '无线']
    if features and not keywords:
        # Preserve the existing free-text fallback for unfamiliar product names.
        if noun := NOUN_PATTERN.search(remaining):
            keywords.append(noun.group())
    if keywords:
        keywords.extend(features)
    return list(dict.fromkeys(keywords))


def required_terms(keywords):
    """A host qualifies a requested accessory; an included accessory qualifies its host."""
    parts = [(word, *phrase_parts(word)) for word in keywords]
    nouns = {noun for _, noun, qualifiers in parts if qualifiers not in INCLUSION}
    accessory_request = bool(nouns.intersection(ACCESSORIES))
    terms = []
    for word, noun, qualifiers in parts:
        attachment = qualifiers in INCLUSION or (noun == '车锁' and '自行车' in nouns)
        host = accessory_request and noun and noun not in ACCESSORIES
        terms.append((word, not (attachment or host)))
    return terms
