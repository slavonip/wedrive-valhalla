"""Правка вставки патча 32 в SetReverseConnection: там предшественник называется rev_pred.

Путь объявляется РОВНО как у остальных патчей — `SRC = "/src/valhalla"` отдельной строкой, а имя
файла приклеивается через os.path.join. Раньше здесь стоял путь целиком, одной строкой, и
apply-patches.sh его не подменял: он ищет точное `SRC = "/src/valhalla"` ВМЕСТЕ с закрывающей
кавычкой. Патч тогда правил настоящий /src/valhalla вместо указанного дерева, находил там свою
работу с прошлого раза, печатал «уже исправлено» и выходил с кодом 0. Целевое дерево оставалось с
ДВУМЯ одинаковыми вставками патча 32, и все тринадцать диагностических патчей после него падали на
«ожидал 1 совпадение, нашёл 2». В контейнере это не проявлялось: там дерево и было /src/valhalla.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/thor/bidirectional_astar.cc")
s = io.open(P, encoding="utf-8").read()
OLD = """    c = rev_pred.cost().cost + oppcost + fwd_pred.transition_cost().cost;
  }

  // WEDRIVE trace connection: каждое соединение, а не только первое. Место встречи и его
  // стоимость — это и есть ответ на вопрос, почему выбран один путь, а не другой.
  if (wedrive_debug_bidir() && ++wedrive_conn_count <= 12) {
    auto t = graphreader.GetGraphTile(pred.edgeid());
    midgard::PointLL ll;
    if (t) {
      ll = t->get_node_ll(pred.endnode());
    }
    std::cerr << "WEDRIVE CONN #" << wedrive_conn_count << "  cost=" << c
              << "  ребро=" << pred.edgeid().value << " регион=" << pred.edgeid().region()"""
NEW = """    c = rev_pred.cost().cost + oppcost + fwd_pred.transition_cost().cost;
  }

  // WEDRIVE trace connection: каждое соединение, а не только первое. Место встречи и его
  // стоимость — это и есть ответ на вопрос, почему выбран один путь, а не другой.
  if (wedrive_debug_bidir() && ++wedrive_conn_count <= 12) {
    auto t = graphreader.GetGraphTile(rev_pred.edgeid());
    midgard::PointLL ll;
    if (t) {
      ll = t->get_node_ll(rev_pred.endnode());
    }
    std::cerr << "WEDRIVE CONN #" << wedrive_conn_count << "  cost=" << c
              << "  ребро=" << rev_pred.edgeid().value << " регион=" << rev_pred.edgeid().region()"""
if "rev_pred.edgeid().value" in s:
    print("   уже исправлено")
else:
    assert s.count(OLD) == 1, "не нашёл reverse-вставку (%d)" % s.count(OLD)
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("   reverse-вставка переведена на rev_pred")
