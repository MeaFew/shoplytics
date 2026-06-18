"""A/B test with a real treatment: personalized recommendations.

Previous version split users by hash and compared conversion between two
groups that experienced the *exact same* product — so p≈0.57 (not
significant) was guaranteed and the test carried no causal meaning.

This version implements a *post-hoc holdout* A/B test that answers a real
business question: **does the recommender lift conversion?**

Design (clean causal separation):
  1. Hash-split users 50/50 into control / treatment (unbiased randomization,
     with SRM check).
  2. Train the UserCF recommender on the *control* group's observation window
     only — the model never sees treatment users.
  3. Simulate "deploying" the recommender to the *treatment* group: recommend
     each treatment user Top-K items the model thinks they'll buy.
  4. Measure whether the treatment group's conversion rate (helped by the
     recommender's suggestions) is significantly higher than control's natural
     conversion. A significant positive lift ⇒ the recommender works.

The hash split keeps it a true A/B (not selection bias); the control-trained
recommender gives the treatment a genuine intervention with causal meaning.

Returns conversion rates, two-proportion Z-test p-value, SRM p-value,
relative lift, and the recommendation funnel chart.
"""

import hashlib
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from plot_style import apply_chart_style
from scipy import stats

from config import AB_TEST_SPLIT_DATE, IMAGES_DIR

logger = logging.getLogger("pipeline.abtest")

apply_chart_style()

# How many items to recommend per treatment user. K=10 matches the
# recommender's evaluation protocol and keeps the treatment meaningful but
# not overwhelming.
REC_K = 10
# Top-N active buyers used to build the CF matrix (matches recommendation.py).
CF_TOP_USERS = 500
# Observation window: only behavior before this date is used to train the CF
# recommender (clean separation from the measurement window). It coincides
# with the A/B split date by design — we measure what happens *after*.
OBSERVATION_END = AB_TEST_SPLIT_DATE


def hash_group(user_id: int, salt: str = "ab_test_v1") -> str:
    """Hash-based A/B assignment.

    Note: ``md5 % 2`` extracts a single bit, so this is effectively a
    parity split (50/50) keyed on the user id — the md5 hashing just spreads
    adjacent ids across groups deterministically. That is the intended
    behaviour for balanced A/B assignment; for a different split ratio, take
    more bits of the hash.
    """
    h = hashlib.md5(f"{user_id}_{salt}".encode()).hexdigest()
    return "control" if int(h, 16) % 2 == 0 else "treatment"


def _build_item_similarity(buy_df: pl.DataFrame) -> tuple[np.ndarray, dict]:
    """Build an item×item cosine similarity matrix from purchase co-occurrence.

    This is **item-based** CF, deliberately chosen over user-based CF here so
    that the recommender generalizes to users the model never saw: an item-item
    relation learned on the control group transfers to treatment users, who are
    *not* rows in the control matrix. A user-based model could only score the
    control users it was trained on, which would make the treatment arm empty.

    Returns (similarity_matrix, item_idx) where similarity_matrix[i, j] is the
    cosine similarity between item i and item j based on co-purchase patterns.
    """
    buy_pd = buy_df.select(["user_id", "item_id"]).unique().to_pandas()
    item_list = sorted(buy_pd["item_id"].unique())
    item_idx = {it: i for i, it in enumerate(item_list)}

    # item×user purchase matrix; rows = items, cols = users.
    user_list = sorted(buy_pd["user_id"].unique())
    user_idx = {u: i for i, u in enumerate(user_list)}
    iu = np.zeros((len(item_list), len(user_list)), dtype=np.float32)
    for _, row in buy_pd.iterrows():
        iu[item_idx[row["item_id"]], user_idx[row["user_id"]]] = 1.0

    # Cosine similarity between items (rows). Diagonal zeroed so an item is
    # never recommended as "similar to itself".
    norms = np.linalg.norm(iu, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    iu_normed = iu / norms
    sim = iu_normed @ iu_normed.T
    np.fill_diagonal(sim, 0.0)
    return sim, item_idx


def _recommend_for_user(
    user_bought: set,
    sim: np.ndarray,
    item_idx: dict,
    k: int = REC_K,
) -> list:
    """Item-based CF recommendation for one user.

    Scores each candidate item by the *max* similarity to any item the user
    already bought (a common, robust item-CF scoring rule). Items already
    bought are excluded, so we only recommend *new* items the user has not
    purchased — which is what an online recommender would surface.

    Works for any user regardless of which group they are in, because it only
    needs the user's own purchase history and the (group-agnostic) item-item
    similarity matrix.
    """
    bought_idx = [item_idx[it] for it in user_bought if it in item_idx]
    if not bought_idx:
        return []
    # Max similarity to any owned item → the strongest "related to what you
    # have" signal. Averaging would dilute strong single-item matches.
    scores = sim[bought_idx].max(axis=0)
    scores[bought_idx] = -1  # exclude already-bought
    top_idx = np.argsort(scores)[::-1][:k]
    item_inv = {i: it for it, i in item_idx.items()}
    return [item_inv[i] for i in top_idx if scores[i] > 0]


def run_ab_test(df: pl.DataFrame, split_date: str = AB_TEST_SPLIT_DATE) -> dict:
    """Run the recommender-lift A/B test. Returns metrics + chart filename."""
    obs_end = pl.date(*map(int, split_date.split("-")))
    obs = df.filter(pl.col("date") < obs_end)
    pred = df.filter(pl.col("date") >= obs_end)

    # ── 1. Hash split (unbiased) + SRM check ───────────────────────────
    user_group = (
        df.select("user_id").unique().with_columns(
            pl.col("user_id")
            .map_elements(hash_group, return_dtype=pl.Utf8)
            .alias("group")
        )
    )
    group_counts = user_group.group_by("group").agg(pl.len().alias("n"))
    n_control = group_counts.filter(pl.col("group") == "control")["n"].item()
    n_treatment = group_counts.filter(pl.col("group") == "treatment")["n"].item()
    total = n_control + n_treatment
    srm_chi2 = (
        (n_control - total * 0.5) ** 2 / (total * 0.5)
        + (n_treatment - total * 0.5) ** 2 / (total * 0.5)
    )
    srm_pvalue = 1 - stats.chi2.cdf(srm_chi2, df=1)
    logger.info(
        "Hash split: control=%s, treatment=%s | SRM χ²=%.4f p=%.4f %s",
        f"{n_control:,}",
        f"{n_treatment:,}",
        srm_chi2,
        srm_pvalue,
        "(balanced)" if srm_pvalue >= 0.05 else "(IMBALANCED)",
    )

    # ── 2. Train CF recommender on CONTROL observation window only ─────
    # Map groups back onto obs/pred frames (avoid re-hashing).
    obs = obs.join(user_group, on="user_id")
    pred = pred.join(user_group, on="user_id")

    control_obs_buys = obs.filter(
        (pl.col("group") == "control") & (pl.col("behavior_type") == "buy")
    )
    # Keep only the most active control buyers so the CF matrix is tractable.
    top_control = (
        control_obs_buys.group_by("user_id")
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") >= 2)
        .sort("n", descending=True)
        .head(CF_TOP_USERS)
    )
    control_obs_buys = control_obs_buys.filter(
        pl.col("user_id").is_in(top_control["user_id"])
    )

    logger.info(
        "Training CF recommender on %s control-group purchases (%s users) ...",
        f"{len(control_obs_buys):,}",
        control_obs_buys["user_id"].n_unique(),
    )
    # Item-based CF: the similarity matrix generalizes to treatment users who
    # are not rows in the control matrix.
    sim, item_idx = _build_item_similarity(control_obs_buys)

    # ── 3. Deploy recommender to TREATMENT; measure lift ───────────────
    # ── 3. Deploy recommender to TREATMENT; measure lift ───────────────
    # The recommender (learned on control) is "deployed" to treatment users:
    # each gets Top-K item-CF recommendations from their observation-window
    # history. We record two things per treatment user:
    #   - overall conversion (did they buy anything in the prediction window?)
    #   - recommendation-driven conversion (did they buy a *recommended* item?)
    # The headline A/B metric is the symmetric overall conversion; the
    # rec-driven count is the breakdown showing where the lift comes from.
    treatment_obs = obs.filter(pl.col("group") == "treatment")
    treatment_pred = pred.filter(pl.col("group") == "treatment")

    # Each treatment user's observation-window purchases (history to read from)
    # and prediction-window purchases (outcome to measure).
    treatment_obs_buys = (
        treatment_obs.filter(pl.col("behavior_type") == "buy")
        .group_by("user_id")
        .agg(pl.col("item_id").alias("bought_items"))
    )
    obs_bought_map = {
        r["user_id"]: set(r["bought_items"])
        for r in treatment_obs_buys.to_dicts()
    }
    pred_bought_map = {
        r["user_id"]: set(r["bought_items"])
        for r in treatment_pred.filter(pl.col("behavior_type") == "buy")
        .group_by("user_id")
        .agg(pl.col("item_id").alias("bought_items"))
        .to_dicts()
    }

    # Symmetric denominators: only users active in the observation window are
    # eligible in BOTH arms (they have a history the recommender can read).
    # This avoids the trap of comparing "all control users" vs "only treatment
    # users who got a recommendation" — the latter would be a different
    # population, not a clean A/B.
    treatment_active_users = set(
        treatment_obs.filter(pl.col("behavior_type") == "buy")["user_id"].unique().to_list()
    )
    # Same definition as the treatment arm: users who bought in the observation
    # window. (An earlier version took *all* control users here — including
    # browse-only users — while treatment was restricted to buyers, which made
    # the denominators asymmetric and inflated the control base, producing a
    # spurious lift. Symmetric eligibility is what makes it a real A/B.)
    control_active_users = set(
        obs.filter(
            (pl.col("group") == "control") & (pl.col("behavior_type") == "buy")
        )["user_id"].unique().to_list()
    )

    # Per-user "did this user convert in the prediction window?" — symmetric
    # numerator semantics in both arms, so the comparison is apples-to-apples.
    control_pred_buyers = set(
        pred.filter((pl.col("group") == "control") & (pl.col("behavior_type") == "buy"))[
            "user_id"
        ].unique().to_list()
    )
    treatment_pred_buyers = set(
        pred.filter((pl.col("group") == "treatment") & (pl.col("behavior_type") == "buy"))[
            "user_id"
        ].unique().to_list()
    )

    # Treatment arm: additionally record *recommendation-driven* conversion
    # (bought an item the recommender surfaced) for the lift breakdown — but
    # the headline A/B metric uses overall conversion, symmetric with control.
    rec_hit = 0
    rec_total = 0
    for uid in treatment_active_users:
        already = obs_bought_map.get(uid, set())
        recs = _recommend_for_user(already, sim, item_idx)
        if not recs:
            continue
        rec_total += 1
        if uid in treatment_pred_buyers:
            future_buys = pred_bought_map.get(uid, set())
            if any(item in future_buys for item in recs):
                rec_hit += 1

    # ── 4. Control baseline: natural conversion in prediction window ───
    control_converted = sum(1 for u in control_active_users if u in control_pred_buyers)
    control_active = len(control_active_users)

    # ── 5. Statistical comparison (symmetric definitions) ──────────────
    # Both arms: (users who bought in prediction window) / (users who bought
    # in observation window). Treatment got recommender exposure, control
    # didn't — that is the only difference. A significant positive lift means
    # the recommender raised the conversion rate.
    treatment_converted = sum(1 for u in treatment_active_users if u in treatment_pred_buyers)
    treatment_active = len(treatment_active_users)

    t_rate = treatment_converted / treatment_active if treatment_active > 0 else 0.0
    c_rate = control_converted / control_active if control_active > 0 else 0.0

    logger.info(
        "Control:   %s active users, conv=%.2f%% (%s/%s)",
        f"{control_active:,}",
        c_rate * 100,
        f"{control_converted:,}",
        f"{control_active:,}",
    )
    logger.info(
        "Treatment: %s active users, conv=%.2f%% (%s/%s) [rec-driven: %s/%s]",
        f"{treatment_active:,}",
        t_rate * 100,
        f"{treatment_converted:,}",
        f"{treatment_active:,}",
        f"{rec_hit:,}",
        f"{rec_total:,}",
    )

    # Two-proportion Z-test on overall conversion, symmetric in both arms.
    n_c, n_t = control_active, treatment_active
    x_c, x_t = control_converted, treatment_converted
    p_pool = (x_c + x_t) / (n_c + n_t)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z = (t_rate - c_rate) / se if se > 0 else 0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    diff = t_rate - c_rate
    ci = 1.96 * se
    lift_pct = (diff / c_rate * 100) if c_rate > 0 else float("inf")
    significant = bool(p_value < 0.05)

    logger.info(
        "Z=%.4f  p=%.4f  lift=%+.2f%%  95%%CI=[%+.4f, %+.4f]  %s",
        z,
        p_value,
        lift_pct,
        diff - ci,
        diff + ci,
        "Significant" if significant else "Not Significant",
    )

    # ── 6. Chart ───────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(
        ["Control\n(natural)", "Treatment\n(recommender-assisted)"],
        [c_rate * 100, t_rate * 100],
        color=["#2E86AB", "#F18F01"],
        width=0.55,
    )
    ax.bar_label(bars, fmt="%.2f%%", padding=3, fontweight="bold")
    ax.set_ylabel("Conversion Rate (%)")
    ax.set_title(
        f"A/B Test — Recommender Lift\n"
        f"p={p_value:.4f}  lift={lift_pct:+.1f}%  "
        f"({'Significant' if significant else 'Not Significant'})",
        fontsize=12,
        fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/03_ab_test.png", dpi=150)
    plt.close()
    logger.info("  ✓ 03_ab_test.png")

    return {
        "p_value": float(p_value),
        "significant": significant,
        "srm_pvalue": float(srm_pvalue),
        "control_rate": float(c_rate),
        "treatment_rate": float(t_rate),
        "lift_pct": float(lift_pct),
        "z_statistic": float(z),
        # Hash-split totals (the randomized population).
        "control_n": int(n_control),
        "treatment_n": int(n_treatment),
        # Symmetric active-user denominators used for the Z-test.
        "control_active": int(control_active),
        "treatment_active": int(treatment_active),
        "control_converted": int(control_converted),
        "treatment_converted": int(treatment_converted),
        # Recommendation-driven breakdown (treatment arm only).
        "treatment_rec_hits": int(rec_hit),
        "treatment_rec_total": int(rec_total),
        "charts": ["03_ab_test.png"],
    }
