#!/usr/bin/env bash
# Loki multi-region: четыре случая привязки плюс отрицательный тест.
#
#   1. точка глубоко внутри одного региона  -> кандидаты только из него
#   2. точка в перекрытии двух регионов      -> кандидаты ИЗ ОБОИХ, регион не выбран заранее
#   3. origin в A, destination в B           -> маршрут через портал, в обе стороны
#   4. обе точки в перекрытии                -> маршрут, регион выбирает Thor по стоимости
#   -. два региона есть, портала нет         -> NO ROUTE, а не тихий переход в чужой граф
#
# Таблица здесь — ОДИН настоящий погранпереход. Полная таблица «все совпадения в зоне
# перекрытия» ломает recost (см. results/THOR-PROGRESS.md), и это отдельный открытый дефект,
# не имеющий отношения к Loki.
set -u
MD=${MD:-/regions/moldova/tiles}
RO=${RO:-/regions/romania/tiles}
L="docker exec vhdev /tmp/loki_route"

cat > /tmp/portal_one.txt <<'EOF'
70384118415618 140758264856834 0   # 46.8233, 28.1407  Leuseni -> Albita
140758264856834 70384118415618 0   # 46.8233, 28.1407  Albita -> Leuseni
EOF
docker cp /tmp/portal_one.txt vhdev:/tmp/ >/dev/null

CHISINAU="47.0105 28.8638"   # только в MD
BUCHAREST="44.4268 26.1025"  # только в RO
CROSS="46.8233 28.1407"      # в ОБОИХ графах
IASI="47.1585 27.6014"

keep() { grep -E 'кандидатов|МАРШРУТ|NO ROUTE|region lost'; }

echo "########## 1. обе точки глубоко внутри ОДНОГО региона"
$L $MD $RO $CHISINAU 47.0269 28.8416 2>&1 | keep

echo
echo "########## 2. origin в ПЕРЕКРЫТИИ — кандидаты обязаны прийти из обоих регионов"
$L $MD $RO $CROSS $CHISINAU 2>&1 | keep

echo
echo "########## 3. MD -> RO, один портал"
$L $MD $RO $CHISINAU $IASI /tmp/portal_one.txt 2>&1 | keep

echo
echo "########## 3b. RO -> MD, обратное направление"
$L $MD $RO $IASI $CHISINAU /tmp/portal_one.txt 2>&1 | keep

echo
echo "########## 4. ОБЕ точки в перекрытии"
$L $MD $RO $CROSS 46.8260 28.1504 /tmp/portal_one.txt 2>&1 | keep

echo
echo "########## 5. Кишинёв -> Бухарест (Бухареста в графе MD нет вовсе)"
$L $MD $RO $CHISINAU $BUCHAREST /tmp/portal_one.txt 2>&1 | keep

echo
echo "########## ОТРИЦАТЕЛЬНЫЙ: те же точки, портала нет -> обязан быть NO ROUTE"
$L $MD $RO $CHISINAU $IASI 2>&1 | keep
