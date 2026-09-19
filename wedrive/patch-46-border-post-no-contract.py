"""WeDrive patch 46: не стягивать шорткат сквозь пограничный пост.

Расследование +2.8 % на Кишинёв -> Бухарест закончено, и дефект оказался НЕ в multi-region
runtime. Загнанные на один и тот же коридор, composite и монолит совпадают до 2 метров
(469.417 против 469.419) и оценка сходится с recost. Дефект в ТАЙЛАХ, и вот он:

    // baldr/nodeinfo.h
    bool can_contract() const {
      return edge_count() >= 2 && intersection() != IntersectionType::kFork &&
             type() != NodeType::kGate && type() != NodeType::kTollBooth &&
             type() != NodeType::kTollGantry && type() != NodeType::kSumpBuster;
    }

Перечислены все типы узлов, которые сами по себе стоят времени, — кроме kBorderControl, а он
стоит дороже всех:

    c += country_crossing_cost_ * (node->type() == kBorderControl);   // 600 с по умолчанию

Стоимость шортката складывается из стоимости его рёбер; переходы во внутренних узлах в неё не
входят никогда. Значит шорткат, накрывший пост, прячет от поиска 600 секунд.

В когерентной сборке это почти не стреляет: у поста по 4 ребра, потому что через него проходят
проезжие части ОБЕИХ стран, и `edge_count() >= 2` вместе с требованием ровно двух рёбер в
CanContract стяжку не пропускает. Экстракт Geofabrik обрезан по границе, у поста остаётся 2
ребра, и запрет перестаёт работать ровно на границе. Измерено на постах Албица-Леушень:

    узел 46.48059,28.23211   монолит 4 ребра, не накрыт
                             Молдова 2 ребра, накрыт шорткатом id 7257 (2297 м, 6 рёбер)
                             Румыния 2 ребра, накрыт шорткатом id 828  (1747 м, 2 ребра)

Шорткат 7257 — тот самый, что лежит на плохом пути. Два поста по 600 дают 1200 невидимых
секунд, оценка соединения занижена на 1234.44, и коридор через Албицу выигрывает у настоящего
лучшего пути.

Исправление — одно слагаемое в том же перечислении. Шорткаты НЕ отключаются нигде больше.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "valhalla/baldr/nodeinfo.h")
s = io.open(P, encoding="utf-8").read()

OLD = (
    "    return edge_count() >= 2 && intersection() != IntersectionType::kFork &&\n"
    "           type() != NodeType::kGate && type() != NodeType::kTollBooth &&\n"
    "           type() != NodeType::kTollGantry && type() != NodeType::kSumpBuster;\n"
)

NEW = (
    "    // WEDRIVE border post: пост стоит 600 секунд, и эта стоимость висит на УЗЛЕ. Шорткат\n"
    "    // считает только свои рёбра, поэтому накрытый пост исчезает из оценки поиска. Все\n"
    "    // прочие платные типы узлов здесь уже перечислены; kBorderControl был пропущен.\n"
    "    return edge_count() >= 2 && intersection() != IntersectionType::kFork &&\n"
    "           type() != NodeType::kGate && type() != NodeType::kTollBooth &&\n"
    "           type() != NodeType::kTollGantry && type() != NodeType::kSumpBuster &&\n"
    "           type() != NodeType::kBorderControl;\n"
)

NAME = "WEDRIVE border post"
if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    assert s.count(OLD) == 1, "не нашёл can_contract"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("      +    %s" % NAME)

s = io.open(P, encoding="utf-8").read()
print("\n   проверка:")
print("      %s маркер" % ("ok     " if NAME in s else "MISSING"))
print("      %s kBorderControl в перечислении"
      % ("ok     " if "type() != NodeType::kBorderControl;" in s else "MISSING"))
print("      %s прочие типы на месте"
      % ("ok     " if "kSumpBuster &&" in s else "MISSING"))
