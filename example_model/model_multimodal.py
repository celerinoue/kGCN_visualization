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
            "sequences",
            "sequences_len",
            "embedded_layer",
        ]
        return self.get_placeholders(info, config, batch_size, keys, **kwargs)

    def build_model(
        self,
        placeholders,
        info,
        config,
        batch_size,
        feed_embedded_layer=False,
        **kwargs
    ):
        adj_channel_num = info.adj_channel_num
        in_adjs = placeholders["adjs"]
        features = placeholders["features"]
        in_nodes = placeholders["nodes"]
        labels = placeholders["labels"]
        mask = placeholders["mask"]
        enabled_node_nums = placeholders["enabled_node_nums"]
        is_train = placeholders["is_train"]
        dropout_rate = placeholders["dropout_rate"]
        sequences = placeholders["sequences"]
        sequences_len = placeholders["sequences_len"]
        embedded_layer = placeholders["embedded_layer"]

        ###
        ### Graph part
        ###
        # with tf.variable_scope("graph_nn") as scope_part:
        layer = features
        input_dim = info.feature_dim
        # layer: batch_size x graph_node_num x dim
        layer = kgcn.layers.GraphConv(50, adj_channel_num)(layer, adj=in_adjs)
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphDense(50)(layer)
        layer = tf.sigmoid(layer)
        layer = kgcn.layers.GraphGather()(layer)
        graph_output_layer = layer
        graph_output_layer_dim = 32

        ###
        ### Sequence part
        ###
        with tf.variable_scope("seq_nn") as scope_part:
            # Embedding
            embedding_dim = config["embedding_dim"]
            self.embedding_layer = tf.keras.layers.Embedding(
                info.sequence_symbol_num, embedding_dim
            )(sequences)
            layer = embedded_layer if feed_embedded_layer else self.embedding_layer
            # CNN + Pooling
            stride = 4
            layer = K.layers.Conv1D(50, stride, padding="same", activation="relu")(
                layer
            )
            layer = K.layers.MaxPooling1D(stride)(layer)
            # LSTM 1
            output_dim = 32
            layer = K.layers.LSTM(
                output_dim, return_sequences=False, go_backwards=True
            )(layer)
            # layer = tf.squeeze(layer)
            seq_output_layer = layer
            seq_output_layer_dim = layer.shape[1]
        ###
        ### Shared part
        ###
        # 32dim (Graph part)+ 32 dim (Sequence part)
        layer = tf.concat([seq_output_layer, graph_output_layer], axis=1)
        input_dim = seq_output_layer_dim + graph_output_layer_dim
        with tf.variable_scope("shared_nn") as scope_part:
            layer = K.layers.Dense(52)(layer)
            # layer=K.layers.BatchNormalization()(layer)
            layer = tf.nn.relu(layer)
            layer = K.layers.Dense(info.label_dim)(layer)

        prediction = tf.nn.softmax(layer)
        # computing cost and metrics
        cost = mask * tf.nn.softmax_cross_entropy_with_logits(
            labels=labels, logits=layer
        )
        cost_opt = tf.reduce_mean(cost)

        metrics = {}
        cost_sum = tf.reduce_sum(cost)

        correct_count = mask * tf.cast(
            tf.equal(tf.argmax(prediction, 1), tf.argmax(labels, 1)), tf.float32
        )
        metrics["correct_count"] = tf.reduce_sum(correct_count)
        self.out = layer
        return self, prediction, cost_opt, cost_sum, metrics

    def embedding(self, sess, data):
        key = self.placeholders["sequences"]
        feed_dict = {key: data}
        out = sess.run(self.embedding_layer, feed_dict)
        return out
