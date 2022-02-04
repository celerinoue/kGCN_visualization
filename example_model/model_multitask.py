from kgcn.default_model import DefaultModel
import tensorflow as tf

if tf.__version__.split(".")[0] == "2":
    import tensorflow.compat.v1 as tf

    tf.disable_v2_behavior()
    import tensorflow.keras as K
else:
    import tensorflow.contrib.keras as K
import kgcn.layers


class GCN(DefaultModel):
    def build_placeholders(self, info, config, batch_size, **kwargs):
        # input data types (placeholders) of this neural network
        keys = [
            "adjs",
            "nodes",
            "labels",
            "mask",
            "dropout_rate",
            "enabled_node_nums",
            "is_train",
            "features",
            "mask_label",
            "mask_node",
        ]
        return self.get_placeholders(info, config, batch_size, keys, **kwargs)

    def build_model(self, placeholders, info, config, batch_size, **kwargs):
        adj_channel_num = info.adj_channel_num
        embedding_dim = config["embedding_dim"]
        in_adjs = placeholders["adjs"]
        features = placeholders["features"]
        in_nodes = placeholders["nodes"]
        labels = placeholders["labels"]
        mask = placeholders["mask"]
        mask_label = placeholders["mask_label"]
        dropout_rate = placeholders["dropout_rate"]
        is_train = placeholders["is_train"]
        mask_node = placeholders["mask_node"]
        enabled_node_nums = placeholders["enabled_node_nums"]

        layer = features
        input_dim = info.feature_dim
        if features is None:
            layer = K.layers.Embedding(info.all_node_num, embedding_dim)(in_nodes)
            input_dim = embedding_dim
        # layer: batch_size x graph_node_num x dim
        layer = kgcn.layers.GraphConv(256, adj_channel_num)(layer, adj=in_adjs)
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphConv(256, adj_channel_num)(layer, adj=in_adjs)
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphDense(256)(layer)
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphConv(50, adj_channel_num)(layer, adj=in_adjs)
        layer = kgcn.layers.GraphBatchNormalization()(
            layer, max_node_num=info.graph_node_num, enabled_node_nums=enabled_node_nums
        )
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphDense(50)(layer)
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphGather()(layer)
        layer = K.layers.Dense(info.label_dim)(layer)
        ###
        ### multi-task loss
        ###
        prediction = tf.sigmoid(layer)
        # computing cost and metrics
        # cost (batch_size x labels) => batch_size
        if "pos_weight" in info:
            wce = tf.nn.weighted_cross_entropy_with_logits(
                targets=labels, logits=layer, pos_weight=info.pos_weight
            )
            cost = mask * tf.reduce_sum(mask_label * wce, axis=1)
        else:
            ce = tf.nn.sigmoid_cross_entropy_with_logits(labels=labels, logits=layer)
            cost = mask * tf.reduce_sum(mask_label * ce, axis=1)

        cost_opt = tf.reduce_mean(cost)
        metrics = {}
        cost_sum = tf.reduce_sum(cost)

        def binary_activation(x, thresh):
            cond = tf.less(x, tf.ones(tf.shape(x)) * thresh)
            out = tf.where(cond, tf.zeros(tf.shape(x)), tf.ones(tf.shape(x)))
            return out

        correct_count = mask * tf.cast(
            tf.reduce_all(tf.equal(binary_activation(prediction, 0.5), labels), axis=1),
            tf.float32,
        )
        print(correct_count)
        metrics["each_correct_count"] = tf.reduce_sum(correct_count, axis=0)
        metrics["each_count"] = tf.reduce_sum(mask, axis=0)
        metrics["each_cost"] = tf.reduce_sum(cost, axis=0)
        # #data x # task x # class
        prediction = tf.expand_dims(prediction, -1)
        self.out = layer
        return self, prediction, cost_opt, cost_sum, metrics
