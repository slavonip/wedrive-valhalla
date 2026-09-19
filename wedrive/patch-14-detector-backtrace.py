"""WeDrive patch 14: детектор печатает СТЕК, а не только факт.

Три итерации подряд места потери региона искались перебором: посмотреть варнинг, угадать
функцию, пропатчить, пересобрать, прогнать. Каждая итерация — минуты, и каждая находила ОДНО
место. Дешевле один раз научить детектор печатать backtrace: тогда все оставшиеся места видны
за один прогон. Менять инструмент, а не подопытного.
"""
import io
import os

SRC = "/src/valhalla"
P = os.path.join(SRC, "src/baldr/graphreader.cc")
s = io.open(P, encoding="utf-8").read()

if "WEDRIVE backtrace" in s:
    print("      ok   уже применено")
else:
    old = (
        "    if (wedrive_region_lost_.fetch_add(1, std::memory_order_relaxed) == 0) {\n"
        "      std::cerr << \"WEDRIVE WARNING: GetGraphTile received an id with no region while \"\n"
        "                << wedrive_region_dirs_.size()\n"
        "                << \" regions are registered. level=\" << graphid.level()\n"
        "                << \" tileid=\" << graphid.tileid() << \" id=\" << graphid.id()\n"
        "                << \" -- the region tag was dropped upstream of here.\" << std::endl;\n"
        "    }"
    )
    assert s.count(old) == 1, "не нашёл тело детектора"
    new = (
        "    const uint64_t seen = wedrive_region_lost_.fetch_add(1, std::memory_order_relaxed);\n"
        "    if (seen < 6) {\n"
        "      std::cerr << \"WEDRIVE REGION LOST #\" << seen << \": level=\" << graphid.level()\n"
        "                << \" tileid=\" << graphid.tileid() << \" id=\" << graphid.id() << std::endl;\n"
        "      // WEDRIVE backtrace: без стека поиск оставшихся мест — перебор по одному за раз.\n"
        "      void* frames[24];\n"
        "      const int nf = ::backtrace(frames, 24);\n"
        "      char** syms = ::backtrace_symbols(frames, nf);\n"
        "      if (syms) {\n"
        "        for (int i = 1; i < nf && i < 14; ++i) {\n"
        "          std::cerr << \"      \" << syms[i] << std::endl;\n"
        "        }\n"
        "        ::free(syms);\n"
        "      }\n"
        "    }"
    )
    s = s.replace(old, new)
    # Include ставим перед самым первым, каким бы он ни был: путь к graphreader.h в этом файле
    # может быть записан иначе, и угадывать его незачем.
    first = s.index("#include")
    s = s[:first] + "#include <execinfo.h> // WEDRIVE backtrace\n" + s[first:]
    io.open(P, "w", encoding="utf-8").write(s)
    print("      +    WEDRIVE backtrace в детекторе")

s = io.open(P, encoding="utf-8").read()
print("      %s execinfo подключён" % ("ok     " if "#include <execinfo.h>" in s else "MISSING"))
print("      %s backtrace вызывается" % ("ok     " if "::backtrace(frames" in s else "MISSING"))
