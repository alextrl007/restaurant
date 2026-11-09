"""Logica de rotație: cine plătește la următoarea ieșire.

Fiecare persoană are un SOLD:
  - când plătește la o masă cu n persoane prezente: +(n-1)
  - când mănâncă pe banii altcuiva: -1
  - când lipsește: nu se schimbă nimic

La o ieșire plătește, dintre cei prezenți, cel cu soldul cel mai mic.
La egalitate se trage la sorți (tragerea se face în main.py și se salvează).
Soldul se calculează mereu din istoric, deci nu se poate desincroniza.
"""


def compute_stats(members, outings):
    stats = {m: {"name": m, "balance": 0, "paid": 0, "attended": 0} for m in members}
    for o in outings:
        att = [a for a in o["attendees"] if a in stats]
        n = len(att)
        for m in att:
            stats[m]["attended"] += 1
            if m == o["payer"]:
                stats[m]["paid"] += 1
                stats[m]["balance"] += n - 1
            else:
                stats[m]["balance"] -= 1
    return stats


def candidates(stats, present):
    """Cei prezenți cu cel mai mic sold (în ordinea în care au fost dați)."""
    low = min(stats[m]["balance"] for m in present)
    return [m for m in present if stats[m]["balance"] == low]


def ranking(stats, present):
    """Prezenții în ordinea la plată: cel mai mic sold primul."""
    return sorted(present, key=lambda m: (stats[m]["balance"], m))
