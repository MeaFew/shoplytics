# 数据集下载指引

## 推荐数据集：阿里云天池淘宝用户行为数据集

### 数据集信息
- **名称**: UserBehavior.csv
- **来源**: [阿里云天池 - 淘宝用户购物行为数据集](https://tianchi.aliyun.com/dataset/649)
- **时间范围**: 2017年11月25日 ~ 2017年12月3日（9天）
- **数据规模**:
  - 用户数: 987,994
  - 商品数: 4,162,024
  - 商品类目数: 9,439
  - 行为记录总数: 100,150,807
- **文件大小**: 解压后约 3.5 GB

### 字段说明

| 列名 | 类型 | 说明 |
|------|------|------|
| user_id | int | 用户ID（序列化/脱敏） |
| item_id | int | 商品ID（序列化/脱敏） |
| category_id | int | 商品类目ID（序列化/脱敏） |
| behavior_type | string | 行为类型: pv(点击), buy(购买), cart(加购), fav(收藏) |
| timestamp | int | 行为发生时间戳（Unix时间戳，秒级） |

### 下载步骤

1. 访问 [阿里云天池数据集页面](https://tianchi.aliyun.com/dataset/649)
2. 注册/登录阿里云账号
3. 点击「下载数据集」按钮
4. 解压下载的压缩包，得到 `UserBehavior.csv`
5. 将 `UserBehavior.csv` 放入本项目的 `data/raw/` 目录下

### 替代方案（小样本测试）

如果完整数据集太大，可以先使用 GitHub 上的小样本进行测试：
```bash
curl -L -o data/raw/UserBehavior.csv \
  https://raw.githubusercontent.com/wuchong/my-flink-project/master/src/main/resources/UserBehavior.csv
```

### 数据使用声明

本数据集为阿里巴巴提供的公开脱敏数据集，仅用于学习和研究目的。数据中的用户ID、商品ID均为序列化后的匿名标识，不包含任何真实个人信息。

---

## 快速开始

下载数据后，运行以下命令开始分析：

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 数据预处理
python scripts/preprocess.py

# 3. 运行SQL分析（需要DuckDB）
# 详见 sql/README.md

# 4. 运行Python分析
jupyter notebook notebooks/
```
