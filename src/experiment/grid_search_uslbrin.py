import logging
import os
import shutil
import sys
import time

sys.path.append('/home/zju/wlj/SLBRIN')
from src.experiment.common_utils import Distribution, load_query, load_data, copy_dirs, group_data_by_date
from src.spatial_index.uslbrin import USLBRIN

if __name__ == '__main__':
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    import tensorflow as tf

    gpus = tf.config.experimental.list_physical_devices(device_type='GPU')
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    origin_path = "model/origin_slbrin/"
    target_path = "model/compare_uslbrin/"
    if not os.path.exists(target_path):
        os.makedirs(target_path)
    logging.basicConfig(filename=os.path.join(target_path, "log.file"),
                        level=logging.INFO,
                        format="%(message)s")
    index_infos = [
        # prepare
        ("uslbrin_0_0_0", True, -1, 3, True, True, -1, 3, True, True, 0, 0, 0, True),
        # tel
        ("uslbrin_0_0_0", True, -1, 3, True, False, -1, 3, False, True, 0, 0, 0, False),
        ("uslbrin_1_0_0", True, -1, 3, True, False, -1, 3, False, True, 1, 0, 0, False),
        ("uslbrin_2_0_0", True, -1, 3, True, False, -1, 3, False, True, 2, 0, 0, False),
        ("uslbrin_4_0_0", True, -1, 3, True, False, -1, 3, False, True, 4, 0, 0, False),
        ("uslbrin_8_0_0", True, -1, 3, True, False, -1, 3, False, True, 8, 0, 0, False),
        # tef
        ("uslbrin_0_0_0", False, -1, 3, False, True, -1, 3, True, True, 0, 0, 0, False),
        ("uslbrin_0_1_0", False, -1, 3, False, True, -1, 3, True, True, 0, 1, 0, False),
        ("uslbrin_0_2_0", False, -1, 3, False, True, -1, 3, True, True, 0, 2, 0, False),
        ("uslbrin_0_4_0", False, -1, 3, False, True, -1, 3, True, True, 0, 4, 0, False),
        ("uslbrin_0_8_0", False, -1, 3, False, True, -1, 3, True, True, 0, 8, 0, False),
        # ten
        ("uslbrin_0_0_0", False, -1, 3, False, True, -1, 3, True, True, 0, 0, 0, False),
        ("uslbrin_0_0_1", False, -1, 3, False, True, -1, 3, True, True, 0, 0, 1, False),
        ("uslbrin_0_0_2", False, -1, 3, False, True, -1, 3, True, True, 0, 0, 2, False),
        ("uslbrin_0_0_4", False, -1, 3, False, True, -1, 3, True, True, 0, 0, 4, False),
        ("uslbrin_0_0_8", False, -1, 3, False, True, -1, 3, True, True, 0, 0, 8, False),
    ]
    data_distributions = [Distribution.NYCT_SORTED]
    # data_distributions = [Distribution.UNIFORM_10W, Distribution.NORMAL_10W, Distribution.NYCT_10W]
    for data_distribution in data_distributions:
        origin_model_path = origin_path + data_distribution.name
        point_query_list = load_query(data_distribution, 0).tolist()
        update_data_list = load_data(data_distribution, 1)
        # 2013-02-01-08: 1359676800 | 2013-02-02-08: 1359763200 | 2013-02-08-08: 1360281600
        update_data_list = group_data_by_date(update_data_list, 1359676800, 60 * 60 * 4)
        for index_info in index_infos:
            target_model_path = target_path + data_distribution.name + "/" + index_info[0]
            if index_info[-1]:
                # copy the zm_index as the basic
                if os.path.exists(target_model_path):
                    shutil.rmtree(target_model_path)
                copy_dirs(origin_model_path, target_model_path)
            # initial the compared model from the zm_index
            logging.info("*************start %s %s************" % (index_info[0], data_distribution.name))
            start_time = time.time()
            index = USLBRIN(model_path=target_model_path)
            super(USLBRIN, index).load()
            index.build_append(time_interval=60 * 60 * 24,
                               start_time=1356998400,
                               end_time=1359676799,
                               lag=7,
                               predict_step=7,
                               cdf_width=100,
                               child_length=1,
                               cdf_model='var',
                               max_key_model='es',
                               is_init=index_info[9],
                               threshold_err=index_info[10],
                               threshold_err_cdf=index_info[11],
                               threshold_err_max_key=index_info[12],
                               is_retrain=index_info[1],
                               time_retrain=index_info[2],
                               thread_retrain=index_info[3],
                               is_save=index_info[4],
                               is_retrain_delta=index_info[5],
                               time_retrain_delta=index_info[6],
                               thread_retrain_delta=index_info[7],
                               is_save_delta=index_info[8],
                               is_build=index_info[-1])
            index.save()
            end_time = time.time()
            build_time = end_time - start_time
            logging.info("Build time: %s" % build_time)
            structure_size, ie_size = index.size()
            logging.info("Structure size: %s" % structure_size)
            logging.info("Index entry size: %s" % ie_size)
            logging.info("Model precision avg: %s" % index.model_err())
            for update_data in update_data_list:
                index.insert(update_data)
                logging.info("Update data num: %s" % len(update_data))
                io_cost = index.io_cost
                start_time = time.time()
                index.test_point_query(point_query_list)
                end_time = time.time()
                search_time = (end_time - start_time) / len(point_query_list)
                logging.info("Point query time: %s" % search_time)
                logging.info("Point query io cost: %s" % ((index.io_cost - io_cost) / len(point_query_list)))