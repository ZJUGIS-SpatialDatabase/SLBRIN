import logging
import os
import sys
import time

import pandas as pd
from memory_profiler import profile

sys.path.append('/home/zju/wlj/st-learned-index')
from src.spatial_index.common_utils import Region
from src.spatial_index.geohash_model_index import GeoHashModelIndex


@profile(precision=8)
def load_model_size():
    n_list = [2500, 5000, 10000, 20000, 40000]
    model_paths = ["model/gm_index/n_" + str(n) + "/" for n in n_list]
    index = GeoHashModelIndex(model_path=model_path[0])
    index.load()
    index = None
    index = GeoHashModelIndex(model_path=model_path[1])
    index.load()
    index = None
    index = GeoHashModelIndex(model_path=model_path[2])
    index.load()
    index = None
    index = GeoHashModelIndex(model_path=model_path[3])
    index.load()
    index = None
    index = GeoHashModelIndex(model_path=model_path[4])
    index.load()
    index = None


"""
1. 读取数据
2. 设置实验参数
3. 开始实验
3.1 快速构建精度低的
3.2 构建精度高的
"""
if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    logging.basicConfig(filename=os.path.join("model/gm_index/log.file"),
                        level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s",
                        datefmt="%m/%d/%Y %H:%M:%S %p")
    # 1. 读取数据
    # path = '../../data/trip_data_1_100000.csv'
    path = '../../data/trip_data_1_filter.csv'
    train_set_xy = pd.read_csv(path)
    # 2. 设置实验参数
    n_list = [2500, 5000, 10000, 20000, 40000]
    # 3. 开始实验
    # 3.1 快速构建精度低的
    for n in n_list:
        model_path = "model/gm_index/n_" + str(n) + "/"
        index = GeoHashModelIndex(model_path=model_path)
        index_name = index.name
        logging.info("*************start %s************" % model_path)
        start_time = time.time()
        index.build(data=train_set_xy, max_num=n, data_precision=6, region=Region(40, 42, -75, -73),
                    use_threshold=False,
                    threshold=20,
                    core=[1, 128, 1],
                    train_step=500,
                    batch_size=1024,
                    learning_rate=0.01,
                    retrain_time_limit=20,
                    thread_pool_size=1,
                    record=False)
        end_time = time.time()
        build_time = end_time - start_time
        logging.info("Build time: %s" % build_time)
        index.save()
        model_num = len(index.gm_dict)
        logging.info("Model num: %s" % len(index.gm_dict))
        model_precisions = [(nn.max_err - nn.min_err) for nn in index.gm_dict if nn is not None]
        model_precisions_avg = sum(model_precisions) / model_num
        logging.info("Model precision avg: %s" % model_precisions_avg)
        path = '../../data/trip_data_1_point_query.csv'
        point_query_df = pd.read_csv(path, usecols=[1, 2, 3])
        point_query_list = point_query_df.drop("count", axis=1).values.tolist()
        start_time = time.time()
        results = index.point_query(point_query_list)
        end_time = time.time()
        search_time = (end_time - start_time) / len(point_query_list)
        logging.info("Point query time: %s" % search_time)
    load_model_size()
    # 3.2 构建精度高的
    for n in n_list:
        model_path = "model/gm_index/n_" + str(n) + "_precision/"
        index = GeoHashModelIndex(model_path=model_path)
        index_name = index.name
        logging.info("*************start %s************" % model_path)
        start_time = time.time()
        index.build(data=train_set_xy, max_num=n, data_precision=6, region=Region(40, 42, -75, -73),
                    use_threshold=True,
                    threshold=20,
                    core=[1, 128, 1],
                    train_step=500,
                    batch_size=1024,
                    learning_rate=0.01,
                    retrain_time_limit=20,
                    thread_pool_size=6,
                    record=True)
        end_time = time.time()
        build_time = end_time - start_time
        logging.info("Build time: %s" % build_time)
        index.save()
        model_num = len(index.gm_dict)
        logging.info("Model num: %s" % len(index.gm_dict))
        model_precisions = [(nn.max_err - nn.min_err) for nn in index.gm_dict if nn is not None]
        model_precisions_avg = sum(model_precisions) / model_num
        logging.info("Model precision avg: %s" % model_precisions_avg)
        path = '../../data/trip_data_1_point_query.csv'
        point_query_df = pd.read_csv(path, usecols=[1, 2, 3])
        point_query_list = point_query_df.drop("count", axis=1).values.tolist()
        start_time = time.time()
        results = index.point_query(point_query_list)
        end_time = time.time()
        search_time = (end_time - start_time) / len(point_query_list)
        logging.info("Point query time: %s" % search_time)
