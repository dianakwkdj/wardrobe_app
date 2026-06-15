import os
import uuid  # Universally Unique Identifier
import math
from functools import wraps
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy  # Object-Relational Mapping
from PIL import Image, ImageDraw, ImageFont  # Python Imaging Library
from werkzeug.security import check_password_hash, generate_password_hash
# from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
DEFAULT_CATEGORIES = [
    "Головные уборы",
    "Верхняя одежда",
    "Футболки и топы",
    "Рубашки",
    "Брюки и джинсы",
    "Юбки",
    "Платья",
    "Обувь",
    "Аксессуары",
]
SEASONS = ["Весна", "Лето", "Осень", "Зима", "Демисезон", "Всесезон"]
BASE_COLOR_WHEEL = [
    {"value": "желтый", "label": "Желтый", "hex": "#f5e400", "ring": "outer"},
    {"value": "оранжевый", "label": "Оранжевый", "hex": "#ff8a1a", "ring": "outer"},
    {"value": "красный", "label": "Красный", "hex": "#f12d2d", "ring": "outer"},
    {"value": "розовый", "label": "Розовый", "hex": "#c20a61", "ring": "outer"},
    {"value": "фиолетовый", "label": "Фиолетовый", "hex": "#5c005b", "ring": "outer"},
    {"value": "синий", "label": "Синий", "hex": "#4f4bf6", "ring": "outer"},
    {"value": "голубой", "label": "Голубой", "hex": "#00cad8", "ring": "outer"},
    {"value": "зеленый", "label": "Зеленый", "hex": "#57c958", "ring": "outer"},
    {"value": "белый", "label": "Белый", "hex": "#ffffff", "ring": "inner"},
    {"value": "бежевый", "label": "Бежевый", "hex": "#d7c0a3", "ring": "inner"},
    {"value": "коричневый", "label": "Коричневый", "hex": "#8a5a3c", "ring": "inner"},
    {"value": "черный", "label": "Черный", "hex": "#242424", "ring": "inner"},
    {"value": "серый", "label": "Серый", "hex": "#9ea3a8", "ring": "inner"},
]


def _polar_point(cx: float, cy: float, radius: float, angle_degrees: float) -> tuple[float, float]:
    angle = math.radians(angle_degrees - 90)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _ring_segment_path(cx: float, cy: float, inner_radius: float, outer_radius: float, start_angle: float, end_angle: float) -> str:
    outer_start = _polar_point(cx, cy, outer_radius, start_angle)
    outer_end = _polar_point(cx, cy, outer_radius, end_angle)
    inner_end = _polar_point(cx, cy, inner_radius, end_angle)
    inner_start = _polar_point(cx, cy, inner_radius, start_angle)
    large_arc = 1 if abs(end_angle - start_angle) > 180 else 0
    return (
        f"M {outer_start[0]:.3f} {outer_start[1]:.3f} "
        f"A {outer_radius} {outer_radius} 0 {large_arc} 1 {outer_end[0]:.3f} {outer_end[1]:.3f} "
        f"L {inner_end[0]:.3f} {inner_end[1]:.3f} "
        f"A {inner_radius} {inner_radius} 0 {large_arc} 0 {inner_start[0]:.3f} {inner_start[1]:.3f} Z"
    )


def build_color_wheel() -> list[dict]:
    segments: list[dict] = []
    outer = [color for color in BASE_COLOR_WHEEL if color["ring"] == "outer"]
    inner = [color for color in BASE_COLOR_WHEEL if color["ring"] == "inner"]

    for index, color in enumerate(outer):
        step = 360 / len(outer)
        start_angle = -step / 2 + index * step
        end_angle = start_angle + step
        segments.append({
            **color,
            "path": _ring_segment_path(150, 150, 78, 140, start_angle, end_angle),
        })

    for index, color in enumerate(inner):
        step = 360 / len(inner)
        start_angle = -step / 2 + index * step
        end_angle = start_angle + step
        segments.append({
            **color,
            "path": _ring_segment_path(150, 150, 36, 78, start_angle, end_angle),
        })

    return segments


COLOR_WHEEL = build_color_wheel()
OUTFIT_SLOT_CONFIG = [
    {"id": "headwear", "title": "Головной убор", "anchor": "Головные уборы", "categories": ["Головные уборы"]},
    {"id": "top", "title": "Верх", "anchor": "Футболки, рубашки и платья", "categories": ["Футболки и топы", "Рубашки", "Платья"]},
    {"id": "outerwear", "title": "Куртка / пальто", "anchor": "Верхняя одежда", "categories": ["Верхняя одежда"]},
    {"id": "bottom", "title": "Низ", "anchor": "Брюки, джинсы и юбки", "categories": ["Брюки и джинсы", "Юбки"]},
    {"id": "shoes", "title": "Обувь", "anchor": "Обувь", "categories": ["Обувь"]},
    {"id": "accessory", "title": "Аксессуары", "anchor": "Аксессуары", "categories": ["Аксессуары"]},
]
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo12345"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'wardrobe.sqlite'}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "instance").mkdir(parents=True, exist_ok=True)

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")

    clothes = db.relationship("ClothingItem", backref="user", cascade="all, delete-orphan")
    outfits = db.relationship("Outfit", backref="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    clothes = db.relationship("ClothingItem", backref="category")


class ClothingItem(db.Model):
    __tablename__ = "clothes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(50))
    season = db.Column(db.String(20))
    image_filename = db.Column("image_path", db.Text, nullable=False)

    outfits = db.relationship(
        "Outfit",
        secondary="outfit_items",
        back_populates="items",
    )


class OutfitItem(db.Model):
    __tablename__ = "outfit_items"

    outfit_id = db.Column(db.Integer, db.ForeignKey("outfits.id"), primary_key=True)
    clothes_id = db.Column(db.Integer, db.ForeignKey("clothes.id"), primary_key=True)


class Outfit(db.Model):
    __tablename__ = "outfits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    items = db.relationship(
        "ClothingItem",
        secondary="outfit_items",
        back_populates="outfits",
    )


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


@app.context_processor
def inject_common_data():
    return {
        "current_user": current_user(),
        "seasons": SEASONS,
        "color_wheel": COLOR_WHEEL,
    }


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if current_user() is None:
            flash("Для доступа к странице необходимо войти в систему.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Для доступа к странице необходимо войти в систему.", "warning")
                return redirect(url_for("login", next=request.path))
            if user.role != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_image(file_storage) -> str:
    if not file_storage or not file_storage.filename:
        raise ValueError("Выберите файл изображения.")

    raw_filename = file_storage.filename.strip()
    if not allowed_file(raw_filename):
        raise ValueError("Разрешены только изображения PNG, JPG, JPEG и WEBP.")

    extension = raw_filename.rsplit(".", 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = UPLOAD_FOLDER / filename
    file_storage.save(destination)

    try:
        with Image.open(destination) as image:
            image.verify()
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise ValueError("Файл не является корректным изображением.") from exc

    return filename


def delete_image(filename: str) -> None:
    if filename and not filename.startswith("demo_"):
        (UPLOAD_FOLDER / filename).unlink(missing_ok=True)


def user_item_or_404(item_id: int) -> ClothingItem:
    item = db.session.get(ClothingItem, item_id)
    user = current_user()
    if not item or not user or (item.user_id != user.id and user.role != "admin"):
        abort(404)
    return item


def user_outfit_or_404(outfit_id: int) -> Outfit:
    outfit = db.session.get(Outfit, outfit_id)
    user = current_user()
    if not outfit or not user or (outfit.user_id != user.id and user.role != "admin"):
        abort(404)
    return outfit


def parse_selected_item_ids() -> list[int]:
    ids: list[int] = []
    for raw_id in request.form.getlist("item_ids"):
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if item_id not in ids:
            ids.append(item_id)
    return ids


def normalize_season(value: str | None) -> str:
    value = (value or "").strip()
    return value if value in SEASONS else ""


def get_valid_category(category_id: int | None) -> Category | None:
    if category_id is None:
        return None
    return db.session.get(Category, category_id)


def season_matches(item_season: str | None, outfit_season: str | None) -> bool:
    if not item_season or item_season == "Всесезон":
        return True
    if not outfit_season or outfit_season == "Всесезон":
        return True
    if item_season == outfit_season:
        return True
    return item_season == "Демисезон" and outfit_season in {"Весна", "Осень", "Демисезон"}


def category_group(category_name: str) -> str:
    groups = {
        "Головные уборы": "headwear",
        "Верхняя одежда": "outerwear",
        "Футболки и топы": "top",
        "Рубашки": "top",
        "Брюки и джинсы": "bottom",
        "Юбки": "bottom",
        "Платья": "onepiece",
        "Обувь": "shoes",
        "Аксессуары": "accessory",
    }
    return groups.get(category_name, "other")


def outfit_slot_for_item(item: ClothingItem) -> str:
    category_name = item.category.name if item.category else ""
    group = category_group(category_name)
    if group == "onepiece":
        return "top"
    mapping = {
        "headwear": "headwear",
        "top": "top",
        "outerwear": "outerwear",
        "bottom": "bottom",
        "shoes": "shoes",
        "accessory": "accessory",
    }
    return mapping.get(group, "accessory")


def canonical_color(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.lower().strip().replace("ё", "е")
    synonyms = {
        "белый": ["бел", "молоч", "айвори"],
        "бежевый": ["беж", "крем", "песоч"],
        "коричневый": ["корич", "кофе", "шокол"],
        "черный": ["черн"],
        "серый": ["сер"],
        "красный": ["крас", "бордов", "малинов"],
        "розовый": ["роз"],
        "оранжевый": ["оранж", "персик", "террак"],
        "желтый": ["желт", "горч"],
        "зеленый": ["зелен", "изумруд", "мят", "олив"],
        "голубой": ["голуб", "небес"],
        "синий": ["син", "деним", "джинс"],
        "фиолетовый": ["фиолет", "лаванд"],
    }
    for canonical, words in synonyms.items():
        if any(word in normalized for word in words):
            return canonical
    return normalized


def color_group(color: str | None) -> str:
    normalized = canonical_color(color)
    neutral = {"белый", "бежевый", "коричневый", "черный", "серый"}
    warm = {"красный", "розовый", "оранжевый", "желтый"}
    cool = {"зеленый", "голубой", "синий", "фиолетовый"}
    if normalized in neutral:
        return "neutral"
    if normalized in warm:
        return "warm"
    if normalized in cool:
        return "cool"
    return "unknown"


def season_item_rank(item: ClothingItem, outfit_season: str | None) -> int:
    if not outfit_season:
        return 0
    item_season = normalize_season(item.season)
    if not item_season or item_season == "Всесезон":
        return 8
    if item_season == outfit_season:
        return 18
    if item_season == "Демисезон" and outfit_season in {"Весна", "Осень", "Демисезон"}:
        return 14
    if outfit_season == "Демисезон" and item_season in {"Весна", "Осень"}:
        return 12
    return 0


def item_season_allowed(item: ClothingItem, outfit_season: str | None) -> bool:
    if not outfit_season:
        return True
    return season_matches(item.season, outfit_season)


def color_preference_rank(item: ClothingItem, favorite_color: str | None) -> int:
    if not favorite_color:
        return 0
    item_color = canonical_color(item.color)
    favorite_color = canonical_color(favorite_color)
    if not item_color:
        return 0
    if item_color == favorite_color:
        return 22
    if color_group(item_color) == color_group(favorite_color):
        return 10
    if color_group(item_color) == "neutral":
        return 8
    return 0


def neutral_color_bonus(item: ClothingItem) -> int:
    return 5 if color_group(item.color) == "neutral" else 0


def grouped_items_for_form(items: list[ClothingItem]):
    groups = []
    for slot in OUTFIT_SLOT_CONFIG:
        slot_items = [item for item in items if outfit_slot_for_item(item) == slot["id"]]
        groups.append({**slot, "items": slot_items})
    return groups


def choose_best_item(candidates, selected_items, favorite_color, outfit_season, same_slot_selected=False):
    selected_ids = {item.id for item in selected_items}
    pool = [item for item in candidates if item.id not in selected_ids]
    if not pool and same_slot_selected:
        pool = list(candidates)
    if not pool:
        return None

    selected_color_families = {color_group(item.color) for item in selected_items if color_group(item.color) != "unknown"}
    selected_canon_colors = {canonical_color(item.color) for item in selected_items if canonical_color(item.color)}

    def rank_item(item):
        result = season_item_rank(item, outfit_season) + color_preference_rank(item, favorite_color)
        result += neutral_color_bonus(item)
        canon = canonical_color(item.color)
        family = color_group(item.color)
        if canon and canon in selected_canon_colors:
            result += 8
        if family != "unknown" and family in selected_color_families:
            result += 6
        if item_season_allowed(item, outfit_season):
            result += 4
        return result

    pool.sort(key=lambda item: (rank_item(item), item.id), reverse=True)
    return pool[0]


def enforce_favorite_color_item(selected_items, all_items, favorite_color, outfit_season):
    favorite = canonical_color(favorite_color)
    if not favorite:
        return selected_items

    selected_items = list(selected_items)
    if any(canonical_color(item.color) == favorite for item in selected_items):
        return selected_items

    favorite_candidates = [
        item for item in all_items
        if canonical_color(item.color) == favorite
    ]
    if not favorite_candidates:
        return selected_items

    slot_priority = {
        "top": 6,
        "bottom": 5,
        "outerwear": 4,
        "shoes": 3,
        "accessory": 2,
        "headwear": 1,
    }

    def candidate_rank(item):
        slot = outfit_slot_for_item(item)
        return (
            1 if item_season_allowed(item, outfit_season) else 0,
            season_item_rank(item, outfit_season),
            slot_priority.get(slot, 0),
            item.id,
        )

    favorite_item = max(favorite_candidates, key=candidate_rank)
    favorite_slot = outfit_slot_for_item(favorite_item)
    result = []
    replaced = False

    for item in selected_items:
        item_slot = outfit_slot_for_item(item)

        if category_group(favorite_item.category.name) == "onepiece" and item_slot == "bottom":
            continue

        if favorite_slot == "bottom" and item_slot == "top" and category_group(item.category.name) == "onepiece":
            continue

        if item_slot == favorite_slot and not replaced:
            result.append(favorite_item)
            replaced = True
        else:
            result.append(item)

    if not replaced:
        result.append(favorite_item)

    unique_result = []
    used_ids = set()
    for item in result:
        if item.id not in used_ids:
            unique_result.append(item)
            used_ids.add(item.id)

    return unique_result


def generate_outfit_items(user: User, favorite_color: str | None, outfit_season: str | None):
    items = ClothingItem.query.filter_by(user_id=user.id).order_by(ClothingItem.id.desc()).all()
    slot_pools = {slot["id"]: [] for slot in OUTFIT_SLOT_CONFIG}
    for item in items:
        slot_pools[outfit_slot_for_item(item)].append(item)

    selected_items: list[ClothingItem] = []

    base_item = choose_best_item(slot_pools["top"], selected_items, favorite_color, outfit_season)
    if base_item:
        selected_items.append(base_item)

    base_group = category_group(base_item.category.name) if base_item and base_item.category else ""
    is_onepiece = base_group == "onepiece"

    if not is_onepiece:
        bottom_item = choose_best_item(slot_pools["bottom"], selected_items, favorite_color, outfit_season)
        if bottom_item:
            selected_items.append(bottom_item)

    include_outerwear = outfit_season in {"Весна", "Осень", "Зима", "Демисезон"}
    if include_outerwear:
        outerwear_item = choose_best_item(slot_pools["outerwear"], selected_items, favorite_color, outfit_season)
        if outerwear_item:
            selected_items.append(outerwear_item)

    shoes_item = choose_best_item(slot_pools["shoes"], selected_items, favorite_color, outfit_season)
    if shoes_item:
        selected_items.append(shoes_item)

    accessory_item = choose_best_item(slot_pools["accessory"], selected_items, favorite_color, outfit_season)
    if accessory_item:
        selected_items.append(accessory_item)

    if outfit_season in {"Зима", "Демисезон"}:
        headwear_item = choose_best_item(slot_pools["headwear"], selected_items, favorite_color, outfit_season)
        if headwear_item:
            selected_items.append(headwear_item)

    if len(selected_items) < 2:
        fallback = []
        for slot_id in ["top", "bottom", "shoes", "outerwear", "accessory"]:
            item = choose_best_item(slot_pools[slot_id], fallback, favorite_color, outfit_season, same_slot_selected=True)
            if item and item.id not in {x.id for x in fallback}:
                fallback.append(item)
            if len(fallback) >= 3:
                break
        selected_items = fallback

    selected_items = enforce_favorite_color_item(selected_items, items, favorite_color, outfit_season)

    favorite_label = canonical_color(favorite_color).capitalize() if favorite_color else "Базовый"
    season_label = outfit_season or "универсальный"
    suggested_name = f"{favorite_label} образ — {season_label.lower()}"
    suggested_description = (
        f"Автоматически подобранный комплект"
        + (f" с акцентом на цвет: {canonical_color(favorite_color)}." if favorite_color else ".")
    )
    return {
        "items": selected_items,
        "season": outfit_season or "",
        "name": suggested_name,
        "description": suggested_description,
    }


def load_font(size: int = 28):
    for font_name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_demo_item_image(filename: str, title: str, color: str, garment: str, accent: str = "#4b3a2f") -> None:
    destination = UPLOAD_FOLDER / filename
    if destination.exists():
        return

    image = Image.new("RGB", (720, 720), "#f8f3ec")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([36, 36, 684, 684], radius=42, fill="#fffdf9", outline="#e2d3c5", width=4)

    cx = 360
    if garment in {"shirt", "tshirt"}:
        draw.polygon([(250, 210), (310, 160), (360, 205), (410, 160), (470, 210), (430, 295), (430, 515), (290, 515), (290, 295)], fill=color, outline=accent)
        draw.line([(310, 160), (360, 220), (410, 160)], fill=accent, width=5)
    elif garment == "jacket":
        draw.rounded_rectangle([230, 165, 490, 535], radius=28, fill=color, outline=accent, width=5)
        draw.polygon([(230, 175), (335, 185), (305, 330), (230, 285)], fill="#dbc2a4", outline=accent)
        draw.polygon([(490, 175), (385, 185), (415, 330), (490, 285)], fill="#dbc2a4", outline=accent)
        draw.line([(360, 185), (360, 535)], fill=accent, width=4)
        for y in (275, 345, 415):
            draw.ellipse([348, y, 364, y + 16], fill=accent)
    elif garment == "pants":
        draw.rounded_rectangle([260, 160, 460, 260], radius=20, fill=color, outline=accent, width=5)
        draw.polygon([(270, 245), (355, 245), (338, 545), (240, 545)], fill=color, outline=accent)
        draw.polygon([(365, 245), (450, 245), (480, 545), (382, 545)], fill=color, outline=accent)
        draw.line([(360, 245), (360, 545)], fill=accent, width=4)
    elif garment == "shorts":
        draw.rounded_rectangle([245, 230, 475, 335], radius=22, fill=color, outline=accent, width=5)
        draw.polygon([(255, 320), (355, 320), (340, 470), (230, 470)], fill=color, outline=accent)
        draw.polygon([(365, 320), (465, 320), (490, 470), (380, 470)], fill=color, outline=accent)
        draw.line([(360, 320), (360, 468)], fill=accent, width=4)
    elif garment == "shoes":
        draw.rounded_rectangle([190, 380, 365, 485], radius=38, fill=color, outline=accent, width=5)
        draw.rounded_rectangle([355, 380, 530, 485], radius=38, fill=color, outline=accent, width=5)
        draw.arc([160, 335, 370, 480], start=185, end=345, fill=accent, width=5)
        draw.arc([350, 335, 560, 480], start=195, end=355, fill=accent, width=5)
    elif garment == "belt":
        draw.rounded_rectangle([160, 305, 560, 390], radius=24, fill=color, outline=accent, width=5)
        draw.rounded_rectangle([290, 280, 430, 415], radius=18, outline=accent, width=12)
        draw.rectangle([330, 305, 390, 390], fill="#fffdf9")
    elif garment == "bag":
        draw.rounded_rectangle([215, 260, 505, 520], radius=35, fill=color, outline=accent, width=5)
        draw.arc([255, 155, 465, 360], start=180, end=360, fill=accent, width=12)
        draw.line([(245, 350), (495, 350)], fill=accent, width=4)
    else:
        draw.ellipse([220, 180, 500, 520], fill=color, outline=accent, width=5)

    font = load_font(28)
    small_font = load_font(20)
    draw.text((cx, 605), title, fill="#4b3a2f", font=font, anchor="mm")
    draw.text((cx, 642), "demo image", fill="#9a8170", font=small_font, anchor="mm")
    image.save(destination, format="PNG")


def render_outfit_collage(outfit: Outfit, export: bool = False) -> BytesIO:
    canvas_width, canvas_height = ((1200, 1200) if export else (900, 900))
    canvas = Image.new("RGBA", (canvas_width, canvas_height), "white")

    zones = {
        "headwear": (canvas_width * 0.38, canvas_height * 0.03, canvas_width * 0.62, canvas_height * 0.17),
        "top": (canvas_width * 0.06, canvas_height * 0.18, canvas_width * 0.44, canvas_height * 0.50),
        "outerwear": (canvas_width * 0.56, canvas_height * 0.18, canvas_width * 0.94, canvas_height * 0.50),
        "bottom": (canvas_width * 0.06, canvas_height * 0.53, canvas_width * 0.44, canvas_height * 0.86),
        "shoes": (canvas_width * 0.56, canvas_height * 0.55, canvas_width * 0.94, canvas_height * 0.73),
        "accessory": (canvas_width * 0.56, canvas_height * 0.75, canvas_width * 0.94, canvas_height * 0.95),
    }
    zones = {slot: tuple(int(value) for value in box) for slot, box in zones.items()}

    slot_items = {}
    for item in outfit.items:
        slot = outfit_slot_for_item(item)
        slot_items.setdefault(slot, []).append(item)

    for slot_id, items in slot_items.items():
        if slot_id not in zones:
            continue

        x1, y1, x2, y2 = zones[slot_id]
        for index, item in enumerate(items[:2]):
            image_path = UPLOAD_FOLDER / item.image_filename
            if not image_path.exists():
                continue

            try:
                with Image.open(image_path) as image:
                    paste = image.convert("RGBA")
                    max_width = (x2 - x1) - 18
                    max_height = (y2 - y1) - 18
                    if len(items) > 1:
                        max_width = int(max_width * 0.82)
                        max_height = int(max_height * 0.82)

                    paste.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                    offset_x = 0 if len(items) == 1 else (-38 if index == 0 else 38)
                    offset_y = 0 if len(items) == 1 else (index * 22)
                    paste_x = x1 + ((x2 - x1) - paste.width) // 2 + offset_x
                    paste_y = y1 + ((y2 - y1) - paste.height) // 2 + offset_y
                    canvas.alpha_composite(paste, (paste_x, paste_y))
            except Exception:
                continue

    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def create_demo_content() -> None:
    demo_items = [
        {
            "name": "Бежевый жакет",
            "category": "Верхняя одежда",
            "color": "бежевый",
            "season": "Демисезон",
            "filename": "demo_beige_jacket.png",
            "shape": "jacket",
            "hex": "#c9a77f",
            "notes": "Нейтральная верхняя одежда для капсульного гардероба.",
        },
        {
            "name": "Белая футболка",
            "category": "Футболки и топы",
            "color": "белый",
            "season": "Всесезон",
            "filename": "demo_white_tshirt.png",
            "shape": "tshirt",
            "hex": "#f6f1e9",
            "notes": "Базовый верх, сочетается с нейтральными и синими оттенками.",
        },
        {
            "name": "Синие джинсы",
            "category": "Брюки и джинсы",
            "color": "синий",
            "season": "Демисезон",
            "filename": "demo_blue_jeans.png",
            "shape": "pants",
            "hex": "#315f8c",
            "notes": "Базовый низ для повседневных образов.",
        },
        {
            "name": "Коричневые лоферы",
            "category": "Обувь",
            "color": "коричневый",
            "season": "Демисезон",
            "filename": "demo_brown_loafers.png",
            "shape": "shoes",
            "hex": "#6f4a2e",
            "notes": "Обувь поддерживает тёплую бежево-коричневую палитру.",
        },
        {
            "name": "Коричневый ремень",
            "category": "Аксессуары",
            "color": "коричневый",
            "season": "Всесезон",
            "filename": "demo_brown_belt.png",
            "shape": "belt",
            "hex": "#7b5136",
            "notes": "Аксессуар объединяет обувь и верхнюю одежду по цвету.",
        },
        {
            "name": "Голубая льняная рубашка",
            "category": "Рубашки",
            "color": "голубой",
            "season": "Лето",
            "filename": "demo_blue_linen_shirt.png",
            "shape": "shirt",
            "hex": "#9fc7dc",
            "notes": "Лёгкая рубашка для летнего светлого комплекта.",
        },
        {
            "name": "Белые шорты",
            "category": "Брюки и джинсы",
            "color": "белый",
            "season": "Лето",
            "filename": "demo_white_shorts.png",
            "shape": "shorts",
            "hex": "#f2eee6",
            "notes": "Светлый низ для летнего образа.",
        },
        {
            "name": "Белые кеды",
            "category": "Обувь",
            "color": "белый",
            "season": "Лето",
            "filename": "demo_white_sneakers.png",
            "shape": "shoes",
            "hex": "#f7f2ea",
            "notes": "Универсальная обувь для летнего комплекта.",
        },
        {
            "name": "Плетёная сумка",
            "category": "Аксессуары",
            "color": "бежевый",
            "season": "Лето",
            "filename": "demo_woven_bag.png",
            "shape": "bag",
            "hex": "#d9bd8b",
            "notes": "Бежевый аксессуар поддерживает натуральную летнюю палитру.",
        },
    ]

    for item in demo_items:
        make_demo_item_image(item["filename"], item["name"], item["hex"], item["shape"])

    demo_user = User.query.filter_by(username=DEMO_USERNAME).first()
    if demo_user is None:
        demo_user = User(username=DEMO_USERNAME, email="demo@example.com", role="user")
        demo_user.set_password(DEMO_PASSWORD)
        db.session.add(demo_user)
        db.session.flush()

    category_by_name = {category.name: category for category in Category.query.all()}
    existing_names = {item.name for item in ClothingItem.query.filter_by(user_id=demo_user.id).all()}
    created_by_name = {item.name: item for item in ClothingItem.query.filter_by(user_id=demo_user.id).all()}

    for item_data in demo_items:
        if item_data["name"] in existing_names:
            continue
        item = ClothingItem(
            user_id=demo_user.id,
            category_id=category_by_name[item_data["category"]].id,
            name=item_data["name"],
            color=item_data["color"],
            season=item_data["season"],
            image_filename=item_data["filename"],
        )
        db.session.add(item)
        created_by_name[item.name] = item

    db.session.flush()
    created_by_name = {item.name: item for item in ClothingItem.query.filter_by(user_id=demo_user.id).all()}

    demo_outfits = [
        {
            "name": "Бежевый casual",
            "season": "Демисезон",
            "description": "Нейтральная база: бежевый, белый, синий деним и коричневые аксессуары сочетаются между собой по цвету и сезону.",
            "items": ["Бежевый жакет", "Белая футболка", "Синие джинсы", "Коричневые лоферы", "Коричневый ремень"],
        },
        {
            "name": "Летний светлый комплект",
            "season": "Лето",
            "description": "Голубой и белый дают лёгкую летнюю гамму, а бежевый аксессуар добавляет нейтральный акцент.",
            "items": ["Голубая льняная рубашка", "Белые шорты", "Белые кеды", "Плетёная сумка"],
        },
    ]

    existing_outfit_names = {outfit.name for outfit in Outfit.query.filter_by(user_id=demo_user.id).all()}
    for outfit_data in demo_outfits:
        if outfit_data["name"] in existing_outfit_names:
            continue
        outfit_items = [created_by_name[name] for name in outfit_data["items"] if name in created_by_name]
        outfit = Outfit(
            user_id=demo_user.id,
            name=outfit_data["name"],
        )
        db.session.add(outfit)
        db.session.flush()
        outfit.items = outfit_items


def init_database() -> None:
    db.create_all()

    for category_name in DEFAULT_CATEGORIES:
        if not Category.query.filter_by(name=category_name).first():
            db.session.add(Category(name=category_name))
    db.session.flush()

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", email="admin@example.com", role="admin")
        admin.set_password("admin12345")
        db.session.add(admin)

    create_demo_content()
    db.session.commit()


@app.route("/")
def index():
    if current_user():
        return redirect(url_for("wardrobe"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not username or not email or not password:
            flash("Заполните все обязательные поля.", "danger")
        elif password != password_confirm:
            flash("Пароли не совпадают.", "danger")
        elif len(password) < 6:
            flash("Пароль должен содержать не менее 6 символов.", "danger")
        elif User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Пользователь с таким логином или email уже существует.", "danger")
        else:
            user = User(username=username, email=email, role="user")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Регистрация выполнена. Теперь можно войти.", "success")
            return redirect(url_for("login"))

    return render_template("auth/register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            (User.username == login_value) | (User.email == login_value.lower())
        ).first()

        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            flash("Вход выполнен успешно.", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("wardrobe"))
        flash("Неверный логин или пароль.", "danger")

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("index"))


@app.route("/wardrobe")
@login_required
def wardrobe():
    user = current_user()
    query = ClothingItem.query.filter_by(user_id=user.id)

    search = request.args.get("search", "").strip()
    category_id = request.args.get("category_id", type=int)
    season = request.args.get("season", "").strip()
    color = request.args.get("color", "").strip()

    if search:
        query = query.filter(ClothingItem.name.ilike(f"%{search}%"))
    if category_id:
        query = query.filter_by(category_id=category_id)
    if season:
        query = query.filter_by(season=season)
    if color:
        query = query.filter(ClothingItem.color.ilike(f"%{color}%"))

    items = query.order_by(ClothingItem.id.desc()).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template(
        "wardrobe/list.html",
        items=items,
        categories=categories,
        filters={
            "search": search,
            "category_id": category_id,
            "season": season,
            "color": color,
        },
    )


@app.route("/wardrobe/new", methods=["GET", "POST"])
@login_required
def wardrobe_new():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            category_id = request.form.get("category_id", type=int)
            category = get_valid_category(category_id)
            if not name or category is None:
                raise ValueError("Укажите название и корректную категорию предмета одежды.")

            image_filename = save_uploaded_image(request.files.get("image"))
            item = ClothingItem(
                user_id=current_user().id,
                category_id=category.id,
                name=name,
                color=request.form.get("color", "").strip(),
                season=normalize_season(request.form.get("season")),
                image_filename=image_filename,
            )
            db.session.add(item)
            db.session.commit()
            flash("Предмет одежды добавлен.", "success")
            return redirect(url_for("wardrobe"))
        except ValueError as exc:
            flash(str(exc), "danger")

    return render_template("wardrobe/form.html", item=None, categories=categories)


@app.route("/wardrobe/<int:item_id>", methods=["GET", "POST"])
@login_required
def wardrobe_edit(item_id):
    item = user_item_or_404(item_id)
    categories = Category.query.order_by(Category.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id", type=int)
        category = get_valid_category(category_id)

        if not name or category is None:
            flash("Укажите название и корректную категорию предмета одежды.", "danger")
        else:
            item.name = name
            item.category_id = category.id
            item.color = request.form.get("color", "").strip()
            item.season = normalize_season(request.form.get("season"))

            file_storage = request.files.get("image")
            if file_storage and file_storage.filename:
                try:
                    new_filename = save_uploaded_image(file_storage)
                    old_filename = item.image_filename
                    item.image_filename = new_filename
                    delete_image(old_filename)
                except ValueError as exc:
                    flash(str(exc), "danger")
                    return render_template("wardrobe/form.html", item=item, categories=categories)

            db.session.commit()
            flash("Изменения сохранены.", "success")
            return redirect(url_for("wardrobe"))

    return render_template("wardrobe/form.html", item=item, categories=categories)


@app.route("/wardrobe/<int:item_id>/delete", methods=["POST"])
@login_required
def wardrobe_delete(item_id):
    item = user_item_or_404(item_id)
    affected_outfits = list(item.outfits)
    for outfit in affected_outfits:
        outfit.items = [outfit_item for outfit_item in outfit.items if outfit_item.id != item.id]
        if not outfit.items:
            db.session.delete(outfit)

    delete_image(item.image_filename)
    db.session.delete(item)
    db.session.commit()
    flash("Предмет одежды удалён. Связанные образы обновлены.", "info")
    return redirect(url_for("wardrobe"))


@app.route("/wardrobe/<int:item_id>/download")
@login_required
def wardrobe_download(item_id):
    item = user_item_or_404(item_id)
    path = UPLOAD_FOLDER / item.image_filename
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=f"{item.name}{path.suffix}")


@app.route("/outfits")
@login_required
def outfits():
    user = current_user()
    outfit_list = Outfit.query.filter_by(user_id=user.id).order_by(Outfit.id.desc()).all()
    return render_template("outfits/list.html", outfits=outfit_list)


@app.route("/outfits/new", methods=["GET", "POST"])
@login_required
def outfit_new():
    user = current_user()
    items = ClothingItem.query.filter_by(user_id=user.id).order_by(ClothingItem.name).all()
    selected_ids: list[int] = []
    form_values = {
        "name": "",
        "season": "",
        "favorite_color": "",
    }

    if request.method == "POST":
        action = request.form.get("action", "save")
        form_values = {
            "name": request.form.get("name", "").strip(),
            "season": normalize_season(request.form.get("season")),
            "favorite_color": request.form.get("favorite_color", "").strip(),
        }

        if action == "generate":
            generated = generate_outfit_items(user, form_values["favorite_color"], form_values["season"])
            selected_ids = [item.id for item in generated["items"]]
            form_values["season"] = form_values["season"] or generated["season"]
            form_values["name"] = form_values["name"] or generated["name"]
            if selected_ids:
                flash("Образ подобран по сезону и любимому цвету.", "success")
            else:
                flash("Недостаточно предметов в гардеробе для автоматической генерации. Добавьте одежду разных категорий.", "warning")
        else:
            selected_ids = parse_selected_item_ids()
            selected_items = []
            if selected_ids:
                selected_items = ClothingItem.query.filter(
                    ClothingItem.user_id == user.id,
                    ClothingItem.id.in_(selected_ids),
                ).all()

            if not form_values["name"]:
                flash("Укажите название образа.", "danger")
            elif not selected_items:
                flash("Выберите хотя бы один предмет одежды.", "danger")
            else:
                outfit = Outfit(
                    user_id=user.id,
                    name=form_values["name"],
                )
                db.session.add(outfit)
                db.session.flush()
                outfit.items = selected_items
                db.session.commit()
                if action == "save_export":
                    return redirect(url_for("outfit_export", outfit_id=outfit.id))
                flash("Образ сохранён.", "success")
                return redirect(url_for("outfits"))

    return render_template(
        "outfits/form.html",
        outfit=None,
        items=items,
        selected_ids=selected_ids,
        item_groups=grouped_items_for_form(items),
        form_values=form_values,
    )


@app.route("/outfits/<int:outfit_id>/edit", methods=["GET", "POST"])
@login_required
def outfit_edit(outfit_id):
    outfit = user_outfit_or_404(outfit_id)
    user = current_user()
    item_owner_id = outfit.user_id if user.role == "admin" else user.id
    items = ClothingItem.query.filter_by(user_id=item_owner_id).order_by(ClothingItem.name).all()
    selected_ids = [item.id for item in outfit.items]
    form_values = {
        "name": outfit.name,
        "season": "",
        "favorite_color": "",
    }

    if request.method == "POST":
        action = request.form.get("action", "save")
        form_values = {
            "name": request.form.get("name", "").strip(),
            "season": normalize_season(request.form.get("season")),
            "favorite_color": request.form.get("favorite_color", "").strip(),
        }

        if action == "generate":
            generated = generate_outfit_items(user, form_values["favorite_color"], form_values["season"])
            selected_ids = [item.id for item in generated["items"]]
            form_values["season"] = form_values["season"] or generated["season"]
            form_values["name"] = form_values["name"] or generated["name"]
            if selected_ids:
                flash("Подобран новый вариант образа.", "success")
            else:
                flash("Не удалось подобрать новый образ автоматически: не хватает подходящих вещей.", "warning")
        else:
            selected_ids = parse_selected_item_ids()
            selected_items = []
            if selected_ids:
                selected_items = ClothingItem.query.filter(
                    ClothingItem.user_id == item_owner_id,
                    ClothingItem.id.in_(selected_ids),
                ).all()

            if not form_values["name"]:
                flash("Укажите название образа.", "danger")
            elif not selected_items:
                flash("Выберите хотя бы один предмет одежды.", "danger")
            else:
                outfit.name = form_values["name"]
                outfit.items = selected_items
                db.session.commit()
                if action == "save_export":
                    return redirect(url_for("outfit_export", outfit_id=outfit.id))
                flash("Образ обновлён.", "success")
                return redirect(url_for("outfits"))

    return render_template(
        "outfits/form.html",
        outfit=outfit,
        items=items,
        selected_ids=selected_ids,
        item_groups=grouped_items_for_form(items),
        form_values=form_values,
    )


@app.route("/outfits/<int:outfit_id>/delete", methods=["POST"])
@login_required
def outfit_delete(outfit_id):
    outfit = user_outfit_or_404(outfit_id)
    db.session.delete(outfit)
    db.session.commit()
    flash("Образ удалён.", "info")
    return redirect(url_for("outfits"))


@app.route("/outfits/<int:outfit_id>/image")
@login_required
def outfit_image(outfit_id):
    outfit = user_outfit_or_404(outfit_id)
    if not outfit.items:
        abort(404)
    buffer = render_outfit_collage(outfit, export=False)
    return send_file(buffer, mimetype="image/png")


@app.route("/outfits/<int:outfit_id>/export")
@login_required
def outfit_export(outfit_id):
    outfit = user_outfit_or_404(outfit_id)
    if not outfit.items:
        abort(404)
    buffer = render_outfit_collage(outfit, export=True)
    return send_file(buffer, mimetype="image/png", as_attachment=True, download_name=f"outfit-{outfit.id}.png")


@app.route("/admin")
@login_required
@role_required("admin")
def admin_panel():
    users = User.query.order_by(User.id).all()
    categories = Category.query.order_by(Category.name).all()
    clothes = ClothingItem.query.order_by(ClothingItem.id.desc()).limit(20).all()
    outfits_list = Outfit.query.order_by(Outfit.id.desc()).limit(20).all()
    stats = {
        "users": User.query.count(),
        "categories": Category.query.count(),
        "clothes": ClothingItem.query.count(),
        "outfits": Outfit.query.count(),
    }
    return render_template(
        "admin/panel.html",
        users=users,
        categories=categories,
        clothes=clothes,
        outfits=outfits_list,
        stats=stats,
    )


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@role_required("admin")
def admin_user_role(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    role = request.form.get("role", "").strip()
    if role not in {"user", "admin"}:
        flash("Некорректная роль пользователя.", "danger")
        return redirect(url_for("admin_panel"))

    user.role = role
    db.session.commit()
    flash("Роль пользователя обновлена.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_user_delete(user_id):
    user = db.session.get(User, user_id)
    admin = current_user()
    if not user:
        abort(404)
    if admin and user.id == admin.id:
        flash("Нельзя удалить свою учетную запись администратора.", "warning")
        return redirect(url_for("admin_panel"))

    for item in list(user.clothes):
        delete_image(item.image_filename)
    db.session.delete(user)
    db.session.commit()
    flash("Пользователь и связанные данные удалены.", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/categories/add", methods=["POST"])
@login_required
@role_required("admin")
def admin_category_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Введите название категории.", "danger")
    elif Category.query.filter_by(name=name).first():
        flash("Такая категория уже существует.", "warning")
    else:
        db.session.add(Category(name=name))
        db.session.commit()
        flash("Категория добавлена.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/categories/<int:category_id>/edit", methods=["POST"])
@login_required
@role_required("admin")
def admin_category_edit(category_id):
    category = db.session.get(Category, category_id)
    if not category:
        abort(404)

    name = request.form.get("name", "").strip()
    if not name:
        flash("Введите название категории.", "danger")
    elif Category.query.filter(Category.id != category.id, Category.name == name).first():
        flash("Такая категория уже существует.", "warning")
    else:
        category.name = name
        db.session.commit()
        flash("Категория обновлена.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_category_delete(category_id):
    category = db.session.get(Category, category_id)
    if not category:
        abort(404)

    if category.clothes:
        flash("Нельзя удалить категорию, пока в ней есть предметы одежды.", "warning")
    else:
        db.session.delete(category)
        db.session.commit()
        flash("Категория удалена.", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/clothes/<int:item_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_clothing_delete(item_id):
    item = db.session.get(ClothingItem, item_id)
    if not item:
        abort(404)

    affected_outfits = list(item.outfits)
    for outfit in affected_outfits:
        outfit.items = [outfit_item for outfit_item in outfit.items if outfit_item.id != item.id]
        if not outfit.items:
            db.session.delete(outfit)

    delete_image(item.image_filename)
    db.session.delete(item)
    db.session.commit()
    flash("Предмет одежды удалён администратором.", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/outfits/<int:outfit_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_outfit_delete(outfit_id):
    outfit = db.session.get(Outfit, outfit_id)
    if not outfit:
        abort(404)

    db.session.delete(outfit)
    db.session.commit()
    flash("Образ удалён администратором.", "info")
    return redirect(url_for("admin_panel"))


@app.errorhandler(403)
def forbidden(_error):
    return render_template("errors.html", title="Доступ запрещён", message="У вас нет прав для просмотра этой страницы."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("errors.html", title="Страница не найдена", message="Запрошенный объект не найден."), 404


with app.app_context():
    init_database()


if __name__ == "__main__":
    app.run(debug=True)
