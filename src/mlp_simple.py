import math
import os.path

import numpy as np
import tensorflow as tf

"""
区别于MLP:
1. 不做任何的中间数据持久化，包括日志/checkpoint
2. 不使用retrain和threshold来提高单个模型的精度
3. 模型fit后只使用最后一个epoch的参数，而不是最优参数
"""


class MLPSimple:
    def __init__(self, train_x, train_x_min, train_x_max, train_y, train_y_min, train_y_max,
                 is_gpu, weight, core, train_step, batch_size, learning_rate):
        # common
        self.name = "MLP"
        # data
        self.train_x = train_x
        self.train_x_min = train_x_min
        self.train_x_max = train_x_max
        self.train_y = train_y
        self.train_y_min = train_y_min
        self.train_y_max = train_y_max
        # model structure
        self.is_gpu = is_gpu
        self.weight = weight
        self.core = core
        self.train_step = train_step
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        # for compute
        self.model = None
        self.matrices = None
        self.min_err = None
        self.max_err = None

    def init_model(self):
        self.model = tf.keras.Sequential()
        for i in range(len(self.core) - 1):
            self.model.add(tf.keras.layers.Dense(units=self.core[i + 1],
                                                 input_dim=self.core[i],
                                                 activation='relu'))
        self.model.add(tf.keras.layers.Dense(units=1))
        optimizer = tf.keras.optimizers.Adam(learning_rate=self.learning_rate)
        self.model.compile(optimizer=optimizer, loss=self.mse)

    def train_simple(self, matrices):
        if self.is_gpu:
            os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            os.environ["CUDA_VISIBLE_DEVICES"] = "0"
            # 不输出报错：This TensorFlow binary is optimized with oneAPI Deep Neural Network Library (oneDNN) to use the
            # following CPU instructions in performance-critical operations:  AVX AVX2
            os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
            gpus = tf.config.experimental.list_physical_devices(device_type='GPU')
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
        else:
            os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        self.init_model()
        if matrices:
            self.set_matrices(matrices)
        self.train_model_simple()

    def train_model_simple(self):
        early_stopping = tf.keras.callbacks.EarlyStopping(monitor='loss',
                                                          patience=self.train_step // 100,
                                                          mode='min',
                                                          verbose=0)
        self.model.fit(self.train_x, self.train_y,
                       epochs=self.train_step,
                       initial_epoch=0,
                       batch_size=self.batch_size,
                       verbose=0,
                       callbacks=[early_stopping])
        self.matrices = self.get_matrices()
        self.min_err, self.max_err = self.get_err()

    def get_matrices(self):
        return self.model.get_weights()

    def set_matrices(self, matrices):
        self.model.set_weights(matrices)

    def mse(self, y_true, y_pred):
        diff = y_true - y_pred
        mse_loss = tf.keras.backend.mean(tf.keras.backend.square(diff), axis=-1)
        return mse_loss

    def mse_and_err_bound(self, y_true, y_pred):
        diff = y_true - y_pred
        range_loss = tf.keras.backend.max(diff) - tf.keras.backend.min(diff)
        diff = y_true - y_pred
        mse_loss = tf.keras.backend.mean(tf.keras.backend.square(diff), axis=-1)
        return self.weight * range_loss + mse_loss

    def batch_predict(self):
        """
        分batch predict来减少内存占用
        避免一次性redict形成size(self.train_x) * 1的tensor造成内存溢出
        """
        train_x_len = len(self.train_x)
        step = 10000
        pres = np.empty(shape=(0, 1))
        for i in range(math.ceil(train_x_len / step)):
            tmp_pres = self.model(self.train_x[i * step:(i + 1) * step].reshape(-1, 1)).numpy()
            pres = np.vstack((pres, tmp_pres))
        return pres.flatten()

    def get_err(self):
        if self.train_y_max == self.train_y_min:
            return 0.0, 0.0
        pres = self.batch_predict()
        pres[pres < 0] = 0
        pres[pres > 1] = 1
        errs = (pres - self.train_y) * (self.train_y_max - self.train_y_min)
        return errs.min(), errs.max()