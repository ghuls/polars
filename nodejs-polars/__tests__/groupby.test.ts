import pl from "@polars";

describe("groupby", () => {
  let df: pl.DataFrame;
  beforeEach(() => {
    df = pl.DataFrame({
      "name": ["a", "b", "a", "c", "b"],
      "foo": [1, 3, 3, 5, 7],
      "bar": [2, 4, 4, 6, 8]
    });
  });

  test("aggList", () => {
    const s = pl.Series("a", [1], pl.Int16);
    const actual = df
      .groupBy("name")
      .aggList()
      .sort("name");

    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_agg_list": [[1, 3], [3, 7], [5]],
      "bar_agg_list": [[2, 4], [4, 8], [6]]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("agg:column", () => {
    const actual = df.groupBy("name").agg({
      "foo": "min"
    })
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_min": [1, 3, 5]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("agg:columns", () => {
    const actual = df.groupBy("name").agg({
      "foo": "min",
      "bar": "sum"
    })
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_min": [1, 3, 5],
      "bar_sum": [6, 12, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("agg:columns:multi_agg", () => {
    const actual = df.groupBy("name").agg({
      "foo": ["min", "first", "last"],
      "bar": "sum"
    })
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_min": [1, 3, 5],
      "foo_first": [1, 3, 5],
      "foo_last": [3, 7, 5],
      "bar_sum": [6, 12, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("count", () => {
    const actual = df.groupBy("name").count()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_count": [2, 2, 1],
      "bar_count": [2, 2, 1]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("first", () => {
    const actual = df.groupBy("name").first()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_first": [1, 3, 5],
      "bar_first": [2, 4, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("head", () => {
    const actual = df
      .groupBy("name")
      .head(1)
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo": [[1], [3], [5]],
      "bar": [[2], [4], [6]]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("last", () => {
    const actual = df
      .groupBy("name")
      .last()
      .sort("name");

    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_last": [3, 7, 5],
      "bar_last": [4, 8, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("tail", () => {
    const actual = df
      .groupBy("name")
      .tail(1)
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo": [[3], [7], [5]],
      "bar": [[4], [8], [6]]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("max", () => {
    const actual = df
      .groupBy("name")
      .max()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_max": [3, 7, 5],
      "bar_max": [4, 8, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("mean", () => {
    const actual = df
      .groupBy("name")
      .mean()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_mean": [2, 5, 5],
      "bar_mean": [3, 6, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("median", () => {
    const actual = df
      .groupBy("name")
      .median()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_median": [2, 5, 5],
      "bar_median": [3, 6, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("min", () => {
    const actual = df
      .groupBy("name")
      .min()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_min": [1, 3, 5],
      "bar_min": [2, 4, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("nUnique", () => {
    const actual = df
      .groupBy("name")
      .nUnique()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_n_unique": [2, 2, 1],
      "bar_n_unique": [2, 2, 1]
    });
    expect(actual).toFrameEqual(expected);
  });
  test("sum", () => {
    const actual = df
      .groupBy("name")
      .sum()
      .sort("name");
    const expected = pl.DataFrame({
      "name": ["a", "b", "c"],
      "foo_sum": [4, 10, 5],
      "bar_sum": [6, 12, 6]
    });
    expect(actual).toFrameEqual(expected);
  });
  test.todo("groups");

});
