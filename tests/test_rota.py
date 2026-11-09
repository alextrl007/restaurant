import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rota import candidates, compute_stats, ranking  # noqa: E402

M = ["Razvan", "Andrei", "Vlad", "Alex", "Dragos", "Zsolt"]


def outing(att, payer):
    return {"attendees": att, "payer": payer}


def test_toti_6_o_runda_complet_soldurile_revin_la_zero():
    outs = [outing(M, p) for p in M]
    stats = compute_stats(M, outs)
    assert all(s["balance"] == 0 for s in stats.values())
    assert all(s["paid"] == 1 and s["attended"] == 6 for s in stats.values())


def test_dupa_o_plata_cu_toti_ceilalti_au_prioritate():
    stats = compute_stats(M, [outing(M, "Razvan")])
    assert stats["Razvan"]["balance"] == 5
    assert all(stats[m]["balance"] == -1 for m in M[1:])
    assert "Razvan" not in candidates(stats, M)


def test_cine_a_platit_nu_plateste_urmatoarele_5_note():
    outs = [outing(M, "Razvan")]
    seen = set()
    # urmatoarele 5 mese, mereu toti 6: Razvan nu e niciodata candidat
    for payer in ["Andrei", "Vlad", "Alex", "Dragos", "Zsolt"]:
        stats = compute_stats(M, outs)
        c = candidates(stats, M)
        assert "Razvan" not in c
        assert payer in c  # cei care nu au platit inca sunt la egalitate
        seen.add(payer)
        outs.append(outing(M, payer))
    # dupa a 6-a masa, toti sunt la zero
    assert all(s["balance"] == 0 for s in compute_stats(M, outs).values())


def test_absentul_asteapta_nu_se_contorizeaza():
    outs = [outing(M, "Razvan"), outing(M[:5], "Andrei")]  # Zsolt lipseste la a doua
    stats = compute_stats(M, outs)
    assert stats["Zsolt"]["balance"] == -1  # doar prima masa
    assert stats["Zsolt"]["attended"] == 1


def test_plata_pentru_mai_putine_persoane():
    stats = compute_stats(M, [outing(["Razvan", "Andrei", "Vlad", "Alex"], "Razvan")])
    assert stats["Razvan"]["balance"] == 3
    assert stats["Andrei"]["balance"] == -1
    assert stats["Dragos"]["balance"] == 0


def test_cel_mai_aproape_cand_nimeni_nu_are_5():
    outs = [outing(M, "Razvan"), outing(M, "Andrei")]
    stats = compute_stats(M, outs)
    # Razvan +4, Andrei +4 (5-1), ceilalti -2
    present = ["Razvan", "Vlad", "Alex"]
    assert candidates(stats, present) == ["Vlad", "Alex"]


def test_ranking_ordine():
    stats = compute_stats(M, [outing(M, "Razvan")])
    assert ranking(stats, ["Razvan", "Vlad"])[0] == "Vlad"


def test_dubla_plata_la_prezenta_mare():
    # Razvan plateste de 2 ori cu 6 prezenti => +10, ceilalti -2
    stats = compute_stats(M, [outing(M, "Razvan"), outing(M, "Razvan")])
    assert stats["Razvan"]["balance"] == 10
    assert stats["Vlad"]["balance"] == -2
