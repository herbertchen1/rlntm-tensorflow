import tensorflow as tf
from utils import *


class RLNTM:

    def __init__(self, params, input_, initial, target,
                 in_move, out_move, mem_move, out_mask):
        self.params = params
        self.input = input_
        self.target = target
        self.in_move = in_move
        self.out_move = out_move
        self.mem_move = mem_move
        self.out_mask = out_mask
        self.initial = initial

        self.hidden
        self.state
        self.prediction
        self.moves
        self.cost
        self.optimize

    @lazy_property
    def mask(self):
        with tf.variable_scope("mask"):
            return tf.reduce_max(tf.abs(self.target), reduction_indices=2)

    @lazy_property
    def length(self):
        with tf.variable_scope("length"):
            return tf.reduce_sum(self.mask, reduction_indices=1)

    @lazy_property
    def hidden(self):
        with tf.variable_scope("hidden"):
            hidden, _ = self.forward
            return hidden

    @lazy_property
    def state(self):
        with tf.variable_scope("state"):
            _, state = self.forward
            return state[0], state[1]

    @lazy_property
    def forward(self):
        with tf.variable_scope("forward"):
            unpacked = tf.unstack(self.initial, axis=0)
            cell = self.params.rnn_cell(self.params.rnn_hidden, state_is_tuple=True)
            hidden, state = tf.nn.dynamic_rnn(
                inputs=self.input,
                cell=cell,
                dtype=tf.float32,
                initial_state=tf.contrib.rnn.LSTMStateTuple(unpacked[0], unpacked[1]),
                sequence_length=self.length)

            return hidden, state

    @lazy_property
    def prediction(self):
        with tf.variable_scope("prediction"):
            num_symbols = int(self.target.get_shape()[2])
            max_length = int(self.target.get_shape()[1])

            weight = tf.Variable(tf.truncated_normal(
                [self.params.rnn_hidden, num_symbols], stddev=0.01))
            bias = tf.Variable(tf.constant(0.1, shape=[num_symbols]))

            output = tf.reshape(self.hidden, [-1, self.params.rnn_hidden])
            prediction = tf.nn.softmax(tf.matmul(output, weight) + bias)
            prediction = tf.reshape(prediction, [-1, max_length, num_symbols])
            return prediction

    @lazy_property
    def moves(self):

        max_length = int(self.target.get_shape()[1])

        with tf.variable_scope("in_move"):
            in_moves = self.params.in_move_table.__len__()

            weight = tf.Variable(tf.truncated_normal(
                [self.params.rnn_hidden, in_moves], stddev=0.01))
            bias = tf.Variable(tf.constant(0.1, shape=[in_moves]))

            output = tf.reshape(self.hidden, [-1, self.params.rnn_hidden])
            in_move_logits = tf.nn.softmax(tf.matmul(output, weight) + bias)
            in_move_logits = tf.reshape(in_move_logits, [-1, max_length, in_moves])

        with tf.variable_scope("mem_move"):
            mem_moves = self.params.mem_move_table.__len__()

            weight = tf.Variable(tf.truncated_normal(
                [self.params.rnn_hidden, mem_moves], stddev=0.01))
            bias = tf.Variable(tf.constant(0.1, shape=[mem_moves]))

            output = tf.reshape(self.hidden, [-1, self.params.rnn_hidden])
            mem_move_logits = tf.nn.softmax(tf.matmul(output, weight) + bias)
            mem_move_logits = tf.reshape(mem_move_logits, [-1, max_length, mem_moves])

        with tf.variable_scope("out_move"):
            out_moves = self.params.out_move_table.__len__()

            weight = tf.Variable(tf.truncated_normal(
                [self.params.rnn_hidden, out_moves], stddev=0.01))
            bias = tf.Variable(tf.constant(0.1, shape=[out_moves]))

            output = tf.reshape(self.hidden, [-1, self.params.rnn_hidden])
            out_move_logits = tf.nn.softmax(tf.matmul(output, weight) + bias)
            out_move_logits = tf.reshape(out_move_logits, [-1, max_length, out_moves])

        return in_move_logits, mem_move_logits, out_move_logits

    @lazy_property
    def cost(self):
        with tf.variable_scope("cost"):
            prediction = tf.clip_by_value(self.prediction, 1e-10, 1.0)
            cost = self.target * tf.log(prediction)
            cost = -tf.reduce_sum(cost, reduction_indices=2) * self.out_mask

            in_move_logits, mem_move_logits, out_move_logits = self.moves

            in_cost = self.in_move * tf.log(in_move_logits)
            in_cost = -tf.reduce_sum(in_cost, reduction_indices=2)

            mem_cost = self.mem_move * tf.log(mem_move_logits)
            mem_cost = -tf.reduce_sum(mem_cost, reduction_indices=2)

            out_cost = self.out_move * tf.log(out_move_logits)
            out_cost = -tf.reduce_sum(out_cost, reduction_indices=2)

            return self._average(cost, is_dup=True) + self._average(in_cost+mem_cost+out_cost)

    @lazy_property
    def optimize(self):
        with tf.variable_scope("optimize"):
            gradient = self.params.optimizer.compute_gradients(self.cost)
            if self.params.gradient_clipping:
                limit = self.params.gradient_clipping
                gradient = [
                    (tf.clip_by_value(g, -limit, limit), v)
                    if g is not None else (None, v)
                    for g, v in gradient
                ]
            optimize = self.params.optimizer.apply_gradients(gradient)
            return optimize

    def _average(self, data, is_dup=False):
        with tf.variable_scope("average"):
            data *= self.mask

            if is_dup:
                data = tf.reduce_sum(data, reduction_indices=1) / (self.length / self.params.dup_factor)
            else:
                data = tf.reduce_sum(data, reduction_indices=1) / self.length

            data = tf.reduce_mean(data)
            return data



