from typing import Tuple

import numpy as np
import pandas as pd
import pytest

from autogluon.timeseries import TimeSeriesPredictor
from autogluon.timeseries.dataset.ts_dataframe import ITEMID, TIMESTAMP, TimeSeriesDataFrame

TARGET_COLUMN = "custom_target"
ITEM_IDS = ["Z", "A", "1", "C"]
DUMMY_MODEL_HPARAMS = {"maxiter": 1, "epochs": 1, "num_batches_per_epoch": 1}


def generate_train_and_test_data(
    prediction_length: int = 1,
    freq: str = "H",
    use_known_covariates: bool = False,
    use_past_covariates: bool = False,
    use_static_features_continuous: bool = False,
    use_static_features_categorical: bool = False,
) -> Tuple[TimeSeriesDataFrame, TimeSeriesDataFrame]:
    min_length = prediction_length * 6
    length_per_item = {item_id: np.random.randint(min_length, min_length + 10) for item_id in ITEM_IDS}
    df_per_item = []
    for idx, (item_id, length) in enumerate(length_per_item.items()):
        start = pd.Timestamp("2020-01-05 15:37") + (idx + 1) * pd.tseries.frequencies.to_offset(freq)
        timestamps = pd.date_range(start=start, periods=length, freq=freq)
        index = pd.MultiIndex.from_product([(item_id,), timestamps], names=[ITEMID, TIMESTAMP])
        columns = {TARGET_COLUMN: np.random.normal(size=length)}
        if use_known_covariates:
            columns["known_A"] = np.random.randint(0, 10, size=length)
            columns["known_B"] = np.random.normal(size=length)
        if use_past_covariates:
            columns["past_A"] = np.random.randint(0, 10, size=length)
            columns["past_B"] = np.random.normal(size=length)
            columns["past_C"] = np.random.normal(size=length)
        df_per_item.append(pd.DataFrame(columns, index=index))

    df = TimeSeriesDataFrame(pd.concat(df_per_item))

    if use_static_features_categorical or use_static_features_continuous:
        static_columns = {}
        if use_static_features_categorical:
            static_columns["static_A"] = np.random.choice(["foo", "bar", "bazz"], size=len(ITEM_IDS))
        if use_static_features_continuous:
            static_columns["static_B"] = np.random.normal(size=len(ITEM_IDS))
        static_df = pd.DataFrame(static_columns, index=ITEM_IDS)
        df.static_features = static_df

    train_data = df.slice_by_timestep(None, -prediction_length)
    test_data = df
    return train_data, test_data


@pytest.mark.parametrize("use_past_covariates", [True, False])
@pytest.mark.parametrize("use_known_covariates", [True, False])
@pytest.mark.parametrize("use_static_features_continuous", [True, False])
@pytest.mark.parametrize("use_static_features_categorical", [True, False])
@pytest.mark.parametrize("ignore_time_index", [True, False])
def test_predictor_smoke_test(
    use_known_covariates,
    use_past_covariates,
    use_static_features_continuous,
    use_static_features_categorical,
    ignore_time_index,
):
    prediction_length = 5
    hyperparameters = {
        "Naive": {},
        "SeasonalNaive": {},
        "ETS": DUMMY_MODEL_HPARAMS,
        "ARIMA": DUMMY_MODEL_HPARAMS,
        "DirectTabular": {},
        "RecursiveTabular": {},
        "DeepAR": DUMMY_MODEL_HPARAMS,
        "SimpleFeedForward": DUMMY_MODEL_HPARAMS,
        "TemporalFusionTransformer": DUMMY_MODEL_HPARAMS,
    }

    train_data, test_data = generate_train_and_test_data(
        prediction_length=prediction_length,
        use_known_covariates=use_known_covariates,
        use_past_covariates=use_past_covariates,
        use_static_features_continuous=use_static_features_continuous,
        use_static_features_categorical=use_static_features_categorical,
    )

    known_covariates_names = [col for col in train_data if col.startswith("known_")]

    predictor = TimeSeriesPredictor(
        target=TARGET_COLUMN,
        prediction_length=prediction_length,
        known_covariates_names=known_covariates_names if len(known_covariates_names) > 0 else None,
        ignore_time_index=ignore_time_index,
    )
    predictor.fit(
        train_data,
        hyperparameters=hyperparameters,
    )
    predictor.score(test_data)
    leaderboard = predictor.leaderboard(test_data)

    assert len(leaderboard) == len(hyperparameters) + 1

    known_covariates = test_data.slice_by_timestep(-prediction_length, None)[known_covariates_names]
    predictions = predictor.predict(train_data, known_covariates=known_covariates)

    if ignore_time_index:
        test_data = test_data.get_reindexed_view(freq="S")
    future_test_data = test_data.slice_by_timestep(-prediction_length, None)

    assert predictions.index.equals(future_test_data.index)
