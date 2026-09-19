"""WeDrive patch 65: region расширяется с 3 бит до 8 — 255 регионов вместо семи.

Семи стран хватало на исследование и не хватает на Европу. Формат карт при этом НЕ меняется:
GraphId несёт регион в битах 46..63 и уже допускает 18 бит (kMaxRegionId = 0x3ffff). Узкое
место одно — метка поиска, и она упакована без единого свободного бита:

    predecessor_                               32
    path_distance_ 25 + restrictions_ 7        32
    edgeid_ 46 + opp_index_ 7 + opp_local_idx_ 7 + mode_ 4   64
    endnode_ 46 + use_ 6 + classification_ 3 + девять флагов 64
    path_id_ 7 + restriction_idx_ 8 + internal_turn_ 2 + пять флагов + mask 7 + region_ 3   32

Итого 40 байт у EdgeLabel и ровно 64 у BDEdgeLabel — кэш-линия. Нужно пять бит, и взять их
можно только там, где предел доказуем.

ПЕРВЫЙ КАНДИДАТ ОТВЕРГНУТ ИЗМЕРЕНИЕМ. Напрашивалось сузить opp_local_idx_ с 7 бит до 3:
в заголовке стоит kMaxLocalEdgeIndex = 7, и казалось, что больше семи там не бывает. Обход
всех рёбер (tools/field_range.cc) показал обратное: в монолите MD+RO+HU 48 рёбер имеют
opp_local_idx до 12. Константа ограничивает массив направлений у узла, а не ширину поля.
Сужение молча испортило бы эти рёбра.

ОТКУДА ВЗЯТЫ ПЯТЬ БИТ:

  predecessor_ 32 -> 28   268 435 455 меток. При 64 байтах на метку это 17 ГБ только под
                          метки — недостижимо ни на телефоне, ни на этой машине. Предел не
                          «вряд ли достигнем», а физический. Значение kInvalidLabel (все 32
                          бита) в поле не влезает, поэтому внутри метки оно хранится своим
                          признаком, а аксессор отдаёт наружу прежнюю константу — глобальный
                          kInvalidLabel не тронут, и все сравнения снаружи работают как прежде.

  mode_ 4 -> 3            TravelMode имеет пять значений (kDrive..kPublicTransit и
                          kMaxTravelMode = 4). Предел задан самим перечислением, и это
                          проверяется static_assert'ом, а не комментарием.

Освободившиеся биты занимают флаги, переехавшие из переполненного 32-битного слова. Сами
слова остаются ровно 32 и 64 бита, размеры классов не меняются — на это тоже стоят
static_assert'ы: EdgeLabel 40, BDEdgeLabel 64.

Старые .gph не пересобираются: в файле региона нет и не было.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/sif/edgelabel.h")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE region 8 bits"

# --- 1. predecessor_ становится битовым полем и принимает четыре флага -----------------------
PRED_OLD = (
    "  // predecessor_: Index to the predecessor edge label information.\n"
    "  // Note: invalid predecessor value uses all 32 bits (so if this needs to\n"
    "  // be part of a bit field make sure kInvalidLabel is changed.\n"
    "  uint32_t predecessor_;\n"
)
PRED_NEW = (
    "  // WEDRIVE region 8 bits: predecessor_ сужен с 32 до 28 бит, чтобы освободить четыре\n"
    "  // бита под флаги, переехавшие из переполненного слова ниже. 268 435 455 меток — это\n"
    "  // 17 ГБ при 64 байтах на метку, то есть предел физический, а не оценочный.\n"
    "  //\n"
    "  // Исходный комментарий предупреждал, что kInvalidLabel занимает все 32 бита. Глобальная\n"
    "  // константа не тронута: внутри метки недействительный предшественник хранится своим\n"
    "  // 28-битным признаком, а аксессор отдаёт наружу прежнее значение.\n"
    "  uint32_t predecessor_ : 28;\n"
    "  // Флаг indicating edge is an unpaved road.\n"
    "  uint32_t unpaved_ : 1;\n"
    "  uint32_t has_measured_speed_ : 1;\n"
    "  // Flag if this edge had HGV access\n"
    "  uint32_t hgv_access_ : 1;\n"
    "  // Flag indicating edge is a bridge.\n"
    "  uint32_t bridge_ : 1;\n"
)

# --- 2. mode_ отдаёт бит, туда же переезжает tunnel_ -----------------------------------------
MODE_OLD = (
    "  uint64_t edgeid_ : 46;\n"
    "  uint64_t opp_index_ : 7;\n"
    "  uint64_t opp_local_idx_ : 7;\n"
    "  uint64_t mode_ : 4;\n"
)
MODE_NEW = (
    "  uint64_t edgeid_ : 46;\n"
    "  uint64_t opp_index_ : 7;\n"
    "  // opp_local_idx_ НЕ сужается: kMaxLocalEdgeIndex = 7 ограничивает массив направлений\n"
    "  // у узла, а не это поле. Измерено на MD+RO+HU: 48 рёбер имеют здесь значение до 12.\n"
    "  uint64_t opp_local_idx_ : 7;\n"
    "  // WEDRIVE region 8 bits: TravelMode имеет пять значений, трёх бит хватает с запасом;\n"
    "  // проверяется static_assert'ом в конце файла.\n"
    "  uint64_t mode_ : 3;\n"
    "  // Flag indicating edge is a tunnel.\n"
    "  uint64_t tunnel_ : 1;\n"
)

# --- 3. переполненное слово отдаёт пять флагов и расширяет region ----------------------------
GROUP_OLD = (
    "  uint32_t path_id_ : 7;\n"
    "  uint32_t restriction_idx_ : 8;\n"
    "  // internal_turn_ Did we make an turn on a short internal edge.\n"
    "  uint32_t internal_turn_ : 2;\n"
    "  // Flag indicating edge is an unpaved road.\n"
    "  uint32_t unpaved_ : 1;\n"
    "  uint32_t has_measured_speed_ : 1;\n"
    "\n"
    "  // Flag if this edge had HGV access\n"
    "  uint32_t hgv_access_ : 1;\n"
    "  // Flag indicating edge is a bridge.\n"
    "  uint32_t bridge_ : 1;\n"
    "  // Flag indicating edge is a tunnel.\n"
    "  uint32_t tunnel_ : 1;\n"
    "\n"
    "  // Mask indicating whether the path started on\n"
    "  // an access restriction with an exemption for local traffic\n"
    "  uint32_t destonly_access_restr_mask_ : 7;\n"
    "\n"
    "  // WEDRIVE region storage: the region this label's edge AND end node belong to.\n"
    "  // Both ids are stored region-less (46 bits each, no room), so this is the only\n"
    "  // copy and the accessors below put it back. 3 bits: regions 1..7, 0 = untagged.\n"
    "  uint32_t region_ : 3;\n"
)
GROUP_NEW = (
    "  uint32_t path_id_ : 7;\n"
    "  uint32_t restriction_idx_ : 8;\n"
    "  // internal_turn_ Did we make an turn on a short internal edge.\n"
    "  uint32_t internal_turn_ : 2;\n"
    "\n"
    "  // Mask indicating whether the path started on\n"
    "  // an access restriction with an exemption for local traffic\n"
    "  uint32_t destonly_access_restr_mask_ : 7;\n"
    "\n"
    "  // WEDRIVE region storage: the region this label's edge AND end node belong to.\n"
    "  // Both ids are stored region-less (46 bits each, no room), so this is the only\n"
    "  // copy and the accessors below put it back.\n"
    "  //\n"
    "  // WEDRIVE region 8 bits: 1..255, 0 = untagged. Пять бит под это освободили\n"
    "  // predecessor_ (32->28) и mode_ (4->3), а пять флагов переехали в те слова.\n"
    "  uint32_t region_ : 8;\n"
)

# --- 4. признак недействительного предшественника --------------------------------------------
ACC_OLD = (
    "  uint32_t predecessor() const {\n"
    "    return predecessor_;\n"
    "  }\n"
)
ACC_NEW = (
    "  uint32_t predecessor() const {\n"
    "    // WEDRIVE region 8 bits: наружу отдаётся прежняя глобальная константа, чтобы все\n"
    "    // сравнения `== kInvalidLabel` за пределами метки остались верными.\n"
    "    return predecessor_ == kWeDriveInvalidPred ? baldr::kInvalidLabel : predecessor_;\n"
    "  }\n"
)

PACK_ANCHOR = "protected:\n"
PACK_HELPER = (
    "protected:\n"
    "  // WEDRIVE region 8 bits: 28-битный признак недействительного предшественника.\n"
    "  static constexpr uint32_t kWeDriveInvalidPred = 0x0fffffffu;\n"
    "  static constexpr uint32_t wedrive_pack_pred(const uint32_t p) {\n"
    "    return p == baldr::kInvalidLabel ? kWeDriveInvalidPred : (p & kWeDriveInvalidPred);\n"
    "  }\n"
    "\n"
)

STATIC_ASSERTS = (
    "\n"
    "// WEDRIVE region 8 bits: перекладка бит обязана оставить размеры прежними. BDEdgeLabel —\n"
    "// ровно кэш-линия, и это не украшение: двунаправленный поиск держит миллионы таких меток.\n"
    "static_assert(sizeof(EdgeLabel) == 40, \"EdgeLabel вырос: перекладка бит не удержала 40 байт\");\n"
    "static_assert(sizeof(BDEdgeLabel) == 64, \"BDEdgeLabel вырос: кэш-линия потеряна\");\n"
    "static_assert(static_cast<uint32_t>(TravelMode::kMaxTravelMode) <= 7,\n"
    "              \"TravelMode перерос три бита mode_\");\n"
    "\n"
)
TAIL_OLD = "} // namespace sif\n} // namespace valhalla\n"

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for label, old in (("predecessor", PRED_OLD), ("mode", MODE_OLD), ("группа", GROUP_OLD),
                       ("аксессор", ACC_OLD), ("хвост", TAIL_OLD)):
        assert s.count(old) == 1, "не нашёл якорь: %s" % label
    assert s.count(PACK_ANCHOR) >= 1, "не нашёл protected:"
    s = (s.replace(PRED_OLD, PRED_NEW)
          .replace(MODE_OLD, MODE_NEW)
          .replace(GROUP_OLD, GROUP_NEW)
          .replace(ACC_OLD, ACC_NEW)
          .replace(PACK_ANCHOR, PACK_HELPER, 1)
          .replace(TAIL_OLD, STATIC_ASSERTS + TAIL_OLD))
    # Все записи в predecessor_ проходят через упаковку.
    s = s.replace("predecessor_(baldr::kInvalidLabel)", "predecessor_(wedrive_pack_pred(baldr::kInvalidLabel))")
    s = s.replace("predecessor_(predecessor)", "predecessor_(wedrive_pack_pred(predecessor))")
    s = s.replace("predecessor_ = predecessor;", "predecessor_ = wedrive_pack_pred(predecessor);")
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
CHECKS = (
    ("region восемь бит", "uint32_t region_ : 8;", True),
    ("трёхбитного region не осталось", "uint32_t region_ : 3;", False),
    ("predecessor 28 бит", "uint32_t predecessor_ : 28;", True),
    ("mode три бита", "uint64_t mode_ : 3;", True),
    ("opp_local_idx не тронут", "uint64_t opp_local_idx_ : 7;", True),
    ("упаковка предшественника", "wedrive_pack_pred", True),
    ("голых записей в predecessor_ нет", "predecessor_ = predecessor;", False),
    ("static_assert на размеры", "sizeof(BDEdgeLabel) == 64", True),
    ("static_assert на TravelMode", "kMaxTravelMode) <= 7", True),
)
for label, needle, want in CHECKS:
    print("      %s %s" % ("ok     " if (needle in s) == want else "MISSING", label))
print("      %d записей упакованы" % s.count("wedrive_pack_pred("))
