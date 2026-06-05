"""
SimpleFuzzyLayer — ANFIS 自訂層 + sklearn 警告抑制

用途:給 anfis_controller.py 用 `from anfis_layer import SimpleFuzzyLayer` 取用,
並在 `tf.keras.models.load_model(..., custom_objects={'SimpleFuzzyLayer': SimpleFuzzyLayer})`
傳入,以解決 Keras 3 載入舊版 .keras 模型時的「Could not locate class SimpleFuzzyLayer」錯誤。

順帶抑制 sklearn 的兩個典型雜訊警告(InconsistentVersionWarning、feature_names UserWarning),
否則 service.log 會被 grid search 每輪 25+ 次警告灌滿。

Pi 上 deploy 時:此檔需與 anfis_controller.py 放在同一目錄。
"""
import warnings
warnings.filterwarnings('ignore', message='X does not have valid feature names')
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')

import tensorflow as tf


class SimpleFuzzyLayer(tf.keras.layers.Layer):
    """ANFIS 的高斯模糊化層(num_mfs 個高斯隸屬度函數,centers/sigmas trainable)"""

    def __init__(self, num_mfs, **kwargs):
        super().__init__(**kwargs)
        self.num_mfs = num_mfs

    def build(self, input_shape):
        self.centers = self.add_weight(
            name='centers',
            shape=(input_shape[-1], self.num_mfs),
            initializer=tf.keras.initializers.RandomUniform(-1.5, 1.5),
            trainable=True)
        self.sigmas = self.add_weight(
            name='sigmas',
            shape=(input_shape[-1], self.num_mfs),
            initializer=tf.keras.initializers.Constant(0.5),
            trainable=True)
        super().build(input_shape)

    def call(self, x):
        expanded = tf.expand_dims(x, -1)
        dist = tf.square(expanded - self.centers)
        return tf.exp(-dist / (2 * tf.square(tf.abs(self.sigmas) + 0.1)))

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'num_mfs': self.num_mfs})
        return cfg

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[1], self.num_mfs)
