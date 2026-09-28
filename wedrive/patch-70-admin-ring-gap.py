"""WeDrive patch 70: кольцо admin-отношения замыкается через малый разрыв (<= 500 м), с записью в лог.

AdminBuilder (src/mjolnir/adminbuilder.cc, to_rings) соединяет отрезки ТОЛЬКО по точному совпадению
концов. Если в самом OSM-отношении есть разрыв — кто-то разрезал/удалил пограничный way и не добавил
замену, — кольцо не замыкается нигде, и страна пропадает целиком («is degenerate and will be
skipped»). Её узлы остаются без страны, frontier пуст.

Измерено 2026-09-28 (Full-Europe run 36367106205, graph UA: FAIL empty frontier). Живой OSM
(Overpass 2026-09-28T03:03Z): у Україна r60199 разрыв ~150 м на границе с Польшей у Володимира —
way 789124507 кончается в 50.8614212,24.1436089, следующий way 223105819 начинается в
50.8626275,24.1446422, соединяющего члена нет. Patch 69 тут ни при чём: в экстракте ничего не
пропало, пропало в самом OSM.

Исправление общее, без исключений по странам:
- если кольцо не продолжается точно, берётся БЛИЖАЙШИЙ свободный конец отрезка ТОГО ЖЕ отношения
  в пределах 500 м, разрыв закрывается прямой хордой, каждое такое соединение пишется в лог
  ("WEDRIVE ring gap joined ... m");
- если цепочка кончилась, а её начало в пределах 500 м от конца, кольцо закрывается хордой.
Никакой новой геометрии кроме одной прямой на разрыв; чужие отношения не трогаются; при точном
совпадении поведение прежнее. Только построение admins.sqlite.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/mjolnir/adminbuilder.cc")
s = io.open(P, encoding="utf-8").read()

NAME = "WEDRIVE admin ring gap"
EDITS = [
    # the loop: exact continuation first, else the nearest free end within the cap
    ("    bg::ring_ll_t ring;\n"
     "    for (auto line_itr = line_lookup.begin(); line_itr != line_lookup.end();\n"
     "         line_itr = line_lookup.find(ring.back())) {\n"
     "      // grab the line segment to add\n"
     "      auto line_index = line_itr->second;\n"
     "      auto& line = lines[line_index];\n"
     "      // we can add this line in the forward direction\n"
     "      if ((ring.empty() && line_itr->first == line.front()) ||\n"
     "          (!ring.empty() && ring.back() == line.front())) {\n"
     "        ring.insert(ring.end(), std::make_move_iterator(line.begin() + !ring.empty()),\n"
     "                    std::make_move_iterator(line.end()));\n"
     "      } // have to add this segment backwards\n"
     "      else {\n"
     "        ring.insert(ring.end(), std::make_move_iterator(line.rbegin() + !ring.empty()),\n"
     "                    std::make_move_iterator(line.rend()));\n"
     "      }\n",
     "    bg::ring_ll_t ring;\n"
     "    // " + NAME + " (patch 70): a relation broken in OSM itself (a member way deleted or split\n"
     "    // without its replacement) never closes on exact ends; bridge a gap of <= kGapM with one\n"
     "    // straight chord to the nearest free end of the SAME relation, and log every join\n"
     "    constexpr double kGapM = 500.0;\n"
     "    bool gap = false;\n"
     "    auto next = [&]() {\n"
     "      gap = false;\n"
     "      auto exact = line_lookup.find(ring.back());\n"
     "      if (exact != line_lookup.end() || line_lookup.empty() || ring.front() == ring.back())\n"
     "        return exact;\n"
     "      auto best = line_lookup.end();\n"
     "      double best_m = kGapM;\n"
     "      for (auto it = line_lookup.begin(); it != line_lookup.end(); ++it) {\n"
     "        double m = ring.back().Distance(it->first);\n"
     "        if (m <= best_m) {\n"
     "          best_m = m;\n"
     "          best = it;\n"
     "        }\n"
     "      }\n"
     "      // the ring's own start is closer: leave it to the closing chord below\n"
     "      if (best != line_lookup.end() && ring.back().Distance(ring.front()) < best_m)\n"
     "        return line_lookup.end();\n"
     "      if (best != line_lookup.end()) {\n"
     "        gap = true;\n"
     "        LOG_WARN(\"WEDRIVE ring gap joined for \" + admin_info.first + \" (\" +\n"
     "                 std::to_string(admin_info.second) + \") \" + std::to_string(best_m) +\n"
     "                 \" m near lat,lon \" + std::to_string(ring.back().y()) + \",\" +\n"
     "                 std::to_string(ring.back().x()));\n"
     "      }\n"
     "      return best;\n"
     "    };\n"
     "    for (auto line_itr = line_lookup.begin(); line_itr != line_lookup.end();\n"
     "         line_itr = next()) {\n"
     "      // grab the line segment to add\n"
     "      auto line_index = line_itr->second;\n"
     "      auto& line = lines[line_index];\n"
     "      // after an exact join the shared point is already in the ring; after a gap it is new\n"
     "      const bool skip = !ring.empty() && !gap;\n"
     "      // we can add this line in the forward direction\n"
     "      if (line_itr->first == line.front()) {\n"
     "        ring.insert(ring.end(), std::make_move_iterator(line.begin() + skip),\n"
     "                    std::make_move_iterator(line.end()));\n"
     "      } // have to add this segment backwards\n"
     "      else {\n"
     "        ring.insert(ring.end(), std::make_move_iterator(line.rbegin() + skip),\n"
     "                    std::make_move_iterator(line.rend()));\n"
     "      }\n"),
    # after the chain ends: close a small gap back to its own start
    ("    // degenerate rings are ignored, unconnected rings or missing relation members cause this\n"
     "    if (ring.size() < 4 || ring.front() != ring.back()) {\n",
     "    if (ring.size() >= 3 && ring.front() != ring.back() &&\n"
     "        ring.back().Distance(ring.front()) <= kGapM) {\n"
     "      LOG_WARN(\"WEDRIVE ring gap closed for \" + admin_info.first + \" (\" +\n"
     "               std::to_string(admin_info.second) + \") \" +\n"
     "               std::to_string(ring.back().Distance(ring.front())) + \" m near lat,lon \" +\n"
     "               std::to_string(ring.back().y()) + \",\" + std::to_string(ring.back().x()));\n"
     "      ring.push_back(ring.front());\n"
     "    }\n"
     "    // degenerate rings are ignored, unconnected rings or missing relation members cause this\n"
     "    if (ring.size() < 4 || ring.front() != ring.back()) {\n"),
]

if NAME in s:
    print("      ok   уже применено: %s" % NAME)
else:
    for old, new in EDITS:
        n = s.count(old)
        if n != 1:
            raise SystemExit("patch 70: ожидал 1 совпадение, нашёл %d:\n%s" % (n, old))
        s = s.replace(old, new)
    io.open(P, "w", encoding="utf-8").write(s)
    print("      ok   %s" % NAME)
