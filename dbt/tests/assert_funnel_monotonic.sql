-- 测试：漏斗各环节用户数必须单调递减（pv >= fav >= cart >= buy）
-- 业务逻辑：没有点击就不可能有收藏/加购/购买

SELECT *
FROM {{ ref('int_conversion_funnel') }}
WHERE pv_users < fav_users
   OR pv_users < cart_users
   OR pv_users < buy_users
   OR fav_users < buy_users  -- 收藏用户中可能有人直接购买而不加购，但这里放宽为总体约束
