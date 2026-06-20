-- 测试：漏斗各环节用户数必须满足因果单调性。
-- 漏斗结构：pv（浏览）→ {fav（收藏）, cart（加购）}（并列意向）→ buy（购买）
--   - pv 是入口：pv_users >= fav_users 且 pv_users >= cart_users 且 pv_users >= buy_users
--   - buy 是出口：buy_users <= fav_users（可放宽，因存在直接购买），
--     但 buy_users 必须 <= pv_users
--   - fav 与 cart 是并列的意向环节，二者无固定大小关系，故不强约束
-- 此前该测试漏掉了 cart >= buy 的检查，且把 fav>=buy 当成硬约束（与并列漏斗矛盾）。

SELECT *
FROM {{ ref('int_conversion_funnel') }}
WHERE pv_users < fav_users
   OR pv_users < cart_users
   OR pv_users < buy_users
   OR cart_users < buy_users  -- 加购意向用户中至少应包含所有"加购后购买"用户
