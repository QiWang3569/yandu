"""Ground smart-search filters in the buyer's own wording before retrieval."""
import re
from decimal import Decimal
from typing import Literal, NamedTuple

from pydantic import Field

from .schemas import CAMPUSES, CATEGORIES, CONDITIONS, ParsedIntent, StrictModel
from .smart_terms import (
    ATTRIBUTES, NOUN_PATTERN, SUBTYPES, normalized, phrase_parts, split_negated_products,
)


# Only a number attached to money or budget wording can constrain the price.
NUMBER = re.compile(r'(?<![a-z\d.])(?:\d+(?:\.\d+)?[k千万]?|[零〇一二两三四五六七八九十百千万]+)', re.I)
RANGE_START = re.compile(r'(' + NUMBER.pattern + r')\s*(?:元|块钱|块)?\s*(?:到|至|[-–~～])$', re.I)
DIGITS = dict(zip('零〇一二两三四五六七八九', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
UNITS = {'十': 10, '百': 100, '千': 1000, '万': 10000, 'k': 1000}
HARD_PREFIX = re.compile(r'(?:预算(?:是|为|上限)?|价格|价位|不(?:要)?超过|别超过|不(?:要)?高于|最高|最多|至多|上限|不多于|不贵于|低于|不到)\s*[:：]?\s*[¥￥]?$')
APPROX_PREFIX = re.compile(r'(?:大约|大概|差不多|约|接近|(?<!附)近)\s*[¥￥]?$')
SPLIT = re.compile(r'[，,。；;！？!?\n]+')
META = re.compile(r'^(?:忽略.*规则|系统指令|输出(?:空|预算|分类)|分类写|不要理会.*需求)')
ROLE = re.compile(r'不接受|不考虑|排除|不要(?!超过|高于)|最好(?:是)?|优先(?:考虑)?|尽量|偏好|必须(?:是)?|一定要')
SOFT = ('最好', '优先', '尽量', '偏好')
EXCLUDE = ('不接受', '不考虑', '排除', '不要')
FEATURE_FIRST = re.compile(r'(' + '|'.join(ATTRIBUTES) + r')优先的?(' + NOUN_PATTERN.pattern + r')', re.I)


def amount(value):
    if value[0].isdigit():
        unit = UNITS.get(value[-1].lower())
        return Decimal(value[:-1]) * unit if unit else Decimal(value)
    if all(c in DIGITS for c in value):
        return Decimal(''.join(str(DIGITS[c]) for c in value))
    total = section = digit = 0
    for char in value:
        if char in DIGITS:
            digit = DIGITS[char]
        elif char == '万':
            total += (section + digit or 1) * 10000
            section = digit = 0
        else:
            section += (digit or 1) * UNITS[char]
            digit = 0
    return Decimal(total + section + digit)


class SearchBudget(NamedTuple):
    maximum: Decimal | None
    around: bool
    product: str
    minimum: Decimal | None = None


class SearchCondition(StrictModel):
    role: Literal['required', 'excluded', 'preferred']
    term: str = Field(min_length=1, max_length=30)
    quote: str = Field(min_length=1, max_length=500)


class SearchFilters(ParsedIntent):
    # This lower bound is grounded in the query after the model has returned its intent.
    min_price: Decimal | None = Field(default=None, ge=0, le=999999, decimal_places=2)
    around_price: bool = False
    conditions: list[SearchCondition] | None = None
    filter_quotes: dict[str, str] = Field(default_factory=dict)
    role_source: Literal['model', 'local', 'reference'] | None = None


class ModelSearchIntent(StrictModel):
    """The wire format uses one source of truth for the role of each condition."""
    conditions: list[SearchCondition] = Field(max_length=36)
    category: str | None = None
    budget_quote: str | None = Field(default=None, min_length=1, max_length=500)
    campus_quote: str | None = Field(default=None, min_length=1, max_length=500)
    condition_quote: str | None = Field(default=None, min_length=1, max_length=500)
    clarification: str | None = Field(default=None, max_length=500)

    def verified(self, query: str) -> SearchFilters:
        quotes = {field: quote for field, quote in (
            ('budget', self.budget_quote), ('campus', self.campus_quote),
            ('condition', self.condition_quote)) if quote is not None}
        if any(q not in query for q in [*(c.quote for c in self.conditions), *quotes.values()]):
            raise ValueError('条件引用必须是用户输入中的连续原文')
        roles = {'required': [], 'excluded': [], 'preferred': []}
        seen = set()
        for condition in self.conditions:
            key = normalized(condition.term)
            if key in seen:
                raise ValueError('同一条件只能出现一次')
            if key in normalized(query) and key not in normalized(condition.quote):
                raise ValueError('引用没有包含原文中对应的条件')
            seen.add(key)
            roles[condition.role].append(condition.term)
        budget = budget_from_text(normalized(self.budget_quote or ''))
        campus = next((c for c in CAMPUSES if c[:2] in (self.campus_quote or '')), None)
        condition = next((g for g in CONDITIONS if normalized(g) in normalized(self.condition_quote or '')), None)
        if ((self.budget_quote and budget.maximum is None) or (self.campus_quote and not campus)
                or (self.condition_quote and not condition)):
            raise ValueError('无法从引用中核实预算、校区或成色')
        return SearchFilters(category=self.category, max_price=budget.maximum, min_price=budget.minimum,
                             around_price=budget.around, campus=campus or '不限校区',
                             condition_grade=condition, keywords=roles['required'],
                             excluded_keywords=roles['excluded'], preferences=roles['preferred'],
                             conditions=self.conditions, filter_quotes=quotes, role_source='model',
                             clarification=self.clarification)


def budget_from_text(text):
    """Separate priced spans from product text without removing digits from model names."""
    free = re.search(r'免费(?!配送|送货|安装|退换|包邮|试用)(?:赠?送的?)?', text)
    spans = [free.span()] if free else []
    budget = None
    minimum = None
    around = False
    for match in NUMBER.finditer(text):
        before, after = text[:match.start()].rstrip(), text[match.end():].lstrip()
        money = re.match(r'^(?:人民币|元|块钱|块)', after)
        rest = after[money.end():].lstrip() if money else after
        if re.match(r'成新|新\b|页|件|个|寸|英寸|毫升|公斤|瓦|gb|hz', rest, re.I):
            continue
        capped = re.match(r'以内|以下|之内|封顶|内(?!存)', rest)
        revised = budget is not None and re.search(r'(?:改成|改为|改到|调整到)$', before)
        range_end = RANGE_START.search(before)
        if re.match(r'^(?:到|至|[-–~～])\s*' + NUMBER.pattern, rest, re.I):
            continue  # consume both endpoints together at the right endpoint
        approx_suffix = re.match(r'(?:左右|上下|出头|来(?=块|元)|多(?!少|件|个|页|寸|天|人|张|本|瓦|[a-z]))(?:块钱|块|元)?', rest, re.I)
        prefix = HARD_PREFIX.search(before) or APPROX_PREFIX.search(before) or revised
        soft = bool(approx_suffix or APPROX_PREFIX.search(before))
        # A minimum price is not an upper bound. Conflicting amounts need clarification.
        if re.search(r'(?:至少|不低于|最低)$', before) or re.match(r'以上|起步|起售', rest):
            if budget is not None and amount(match.group()) > budget:
                return SearchBudget(None, False, text)
            continue
        tagged = money or capped or soft or revised or HARD_PREFIX.search(before) or before.endswith(('¥', '￥'))
        if range_end and (re.search(r'预算|价格|价位|元|块|[¥￥]', text) or re.match(r'^(?:的|买|收|找|$)', rest)):
            tagged = True
        if not tagged:
            continue
        value = amount(match.group())
        if value > 999999 or value != value.quantize(Decimal('.01')):
            continue
        start = prefix.start() if prefix else match.start() - int(before.endswith(('¥', '￥')))
        if range_end:
            left = before[:range_end.start()].rstrip()
            lead = HARD_PREFIX.search(left)
            start = lead.start() if lead else range_end.start()
            revised = bool(re.search(r'(?:改成|改为|改到|调整到)$', left))
        end = match.end() + (len(text[match.end():]) - len(rest))
        suffix = capped or approx_suffix
        if suffix:
            end += suffix.end()
        spans.append((start, end))
        soft = soft and not capped and not re.search(r'(?:不(?:要)?|别)超过|不(?:要)?高于|最多|上限', before[-7:])
        if revised:
            minimum = budget = None
        if range_end:
            low = amount(range_end.group(1))
            if low > 999999 or low != low.quantize(Decimal('.01')):
                continue
            minimum = max(low, minimum or Decimal(0))
            soft = False
        elif soft and approx_suffix and approx_suffix.group().startswith('多'):
            # “两百多” spans the next hundred; “二百五十多” spans the next ten.
            minimum = max(value, minimum or Decimal(0))
            step = Decimal(1).scaleb(value.normalize().as_tuple().exponent)
            value = min(value + step, Decimal(999999))
            soft = False
        if budget is None or (not soft and (around or value < budget)):
            budget, around = value, bool(soft)
    # Replace spans in original coordinates, including adjacent or overlapping markers.
    remainder = list(text)
    for start, end in spans:
        remainder[start:end] = ' ' * (end - start)
    product = ''.join(remainder)
    return SearchBudget(Decimal(0), False, product) if free else SearchBudget(budget, around, product, minimum)


def clauses(query):
    hard, excluded, soft = [], [], []
    query = re.sub(r'(?<=\d)[,，](?=\d{3}(?!\d))', '', query)
    query = FEATURE_FIRST.sub(r'\2，优先\1', query)
    for clause in SPLIT.split(query):
        clause = clause.strip()
        if not clause or META.match(clause):
            continue
        # Offline fallback only. Model-backed searches keep their own interpretation.
        if match := re.fullmatch(r'(.+?)(?:会)?更(?:合我心意|合我意|适合我|喜欢)', clause):
            soft.append(match[1])
            continue
        if re.fullmatch(r'.+?(?:也能接受|也可以|也行)', clause):
            continue
        if match := re.fullmatch(r'(?:看到|如果是)?(.+?)(?:我)?就不(?:买|考虑|要)(?:了)?', clause):
            excluded.append(match[1])
            continue
        # Postpositive 优先 is common in standalone clauses such as “黑色优先”.
        if clause.endswith('优先') and not ROLE.search(clause[:-2]):
            feature = next((a for a in ATTRIBUTES if clause[:-2].lower().endswith(a)), None)
            if feature:
                hard.append(clause[:-(len(feature) + 2)])
                soft.append(feature)
            else:
                soft.append(clause[:-2])
            continue
        target, start = hard, 0
        for marker in ROLE.finditer(clause):
            target.append(clause[start:marker.start()])
            target = soft if marker.group().startswith(SOFT) else excluded if marker.group() in EXCLUDE else hard
            start = marker.end()
        target.append(clause[start:])
    def terms(values):
        return [term for v in values if (term := v.strip().removesuffix('的').strip())]
    hard_text = split_negated_products(' '.join(terms(hard)), excluded)
    return hard_text, terms(excluded), terms(soft)


def grounded(term, text):
    word = normalized(term)
    if not word:
        return False
    if word in text:
        return True
    noun, qualifiers = phrase_parts(word)
    return bool(noun and (noun in text or any(s in text for s in SUBTYPES.get(noun, ())))
                and all(q in text for q in qualifiers))


def merge_roles(parsed_terms, spans):
    result = []
    for span in spans:
        source = normalized(span)
        for part in re.split(r'、|以及|并且|而且', source):
            if not part:
                continue
            simple = re.sub(r'^(?:能|支持|带有|有)', '', part)
            if simple in ATTRIBUTES:
                part = simple
            terms = [term for term in parsed_terms if grounded(term, part)]
            features = [a for a in ATTRIBUTES if a in part]
            if terms and all(any(a in normalized(t) for t in terms) for a in features):
                result.extend(terms)
            else:
                result.append(part)
    return result


def unique_terms(words):
    result = {}
    for word in words:
        if word and len(word) <= 30:
            result.setdefault(normalized(word), word)
    return list(result.values())[:12]


def explicit_category(text):
    for category in CATEGORIES:
        if category in text:
            return category
        for part in category.split('与'):
            if re.search(r'(?:只看|分类选|类目选)' + part + '|' + part + r'类', text):
                return category
    return None


def required_from_source(parsed, source):
    required = [w for w in parsed.keywords if grounded(w, source)]
    # Recover literal product nouns when the parser supplied no grounded subject.
    if not any(phrase_parts(w)[0] for w in required):
        nouns = [m.group() for m in NOUN_PATTERN.finditer(source)]
        if nouns and not any(n in normalized(w) for n in nouns for w in required):
            for noun in nouns:
                modifier = next((w for w in required if normalized(w) + noun in source), None)
                if modifier:
                    required.remove(modifier)
                    required.append(modifier + noun)
                else:
                    required.append(noun)
    for feature in ATTRIBUTES:
        if feature in source and not any(feature in normalized(w) for w in required):
            required.append(feature)
    # Preserve the stated product when every proposed keyword came from the model.
    if not required and (parsed.keywords or not parsed.clarification):
        literal = re.sub(r'^(?:我想买|我想要|想买|想要|帮我找|只看|求购|找一个|找个|找|买个|买)\s*', '', source).strip()
        if len(literal) <= 30 and re.search(r'[a-z\u4e00-\u9fff]', literal) and literal not in {'的', '到', '至'}:
            required.append(literal)
    return unique_terms(required)


def ground_intent(query: str, parsed: ParsedIntent):
    """Normalize the local rules parser only; never reinterpret quoted model conditions."""
    hard, exclusions, preferences = clauses(query)
    # “最好静音的鼠标” still asks for a mouse.
    for i, phrase in enumerate(preferences):
        if NOUN_PATTERN.search(hard):
            break
        modifier, separator, product = phrase.rpartition('的')
        if separator and NOUN_PATTERN.search(product):
            hard += ' ' + product
            preferences[i] = modifier
        elif noun := NOUN_PATTERN.search(phrase):
            modifier = phrase[:noun.start()].strip()
            if modifier in ATTRIBUTES and noun.end() == len(phrase):
                hard += ' ' + noun.group()
                preferences[i] = modifier
    budget = budget_from_text(normalized(hard))
    product = budget.product
    campus = next((c for c in CAMPUSES[:-1] if c[:2] in hard), '不限校区')
    grade = next((g for g in CONDITIONS if normalized(g) in product), None)
    category_filter = explicit_category(hard)
    for attribute in (campus, campus[:2], grade, category_filter):
        if attribute:
            product = product.replace(normalized(attribute), ' ')
    if category_filter:
        for part in category_filter.split('与'):
            product = re.sub(r'(?:只看|分类选|类目选)' + part + r'类?|' + part + '类', ' ', product)
    product = re.sub(r'(?:只看|附近)(?:的)?', ' ', product)
    excluded = unique_terms(merge_roles(parsed.excluded_keywords, exclusions))
    preferred = unique_terms(merge_roles(parsed.preferences, preferences))
    required = required_from_source(parsed, product.strip())
    forbidden = {normalized(w) for w in excluded}
    conflicts = forbidden.intersection(normalized(w) for w in required)
    required = [w for w in required if normalized(w) not in forbidden]
    preferred = [w for w in preferred if normalized(w) not in forbidden]
    excluded = [w for w in excluded if normalized(w) not in conflicts]
    category = category_filter or parsed.category
    effective = SearchFilters(**{**parsed.model_dump(exclude={'min_price'}), 'keywords': required,
        'excluded_keywords': excluded, 'preferences': preferred, 'campus': campus,
        'condition_grade': grade, 'category': category, 'max_price': budget.maximum, 'min_price': budget.minimum,
        'clarification': ('请确认是否需要' + '、'.join(sorted(conflicts)) + '。') if conflicts else parsed.clarification})
    return effective, budget.around
