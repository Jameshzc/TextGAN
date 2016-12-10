import re

import tensorflow as tf


fix_re = re.compile(r'''[^a-z0-9"'?.,]+''')
num_re = re.compile(r'[0-9]+')


def fix_word(word):
    word = word.lower()
    word = fix_re.sub('', word)
    word = num_re.sub('#', word)
    return word


def combine_sentences(words, vocab, max_length):
    outputs = []
    output = []
    current = []
    for i, sent in enumerate(words):
        for j, word in enumerate(sent):
            current.append(word)
            if word == vocab.sos_index or j == len(sent) - 1:
                word = vocab.sos_index
                if len(output) + len(current) > max_length:
                    outputs.append(output)
                    output = []
                output.extend(current)
                current = []
                break
    if output:
        outputs.append(output)
    return outputs


def display_sentences(output, vocab):
    '''Display sentences from indices.'''
    for i, sent in enumerate(output):
        print('Sentence %d:' % i, end=' ')
        for word in sent:
            if word == vocab.sos_index:
                print('.', end=' ')
            else:
                print(vocab.vocab[word], end=' ')
        print()
    print()


def read_words(line, chars):
    if chars:
        first = True
    for word in line.split():
        if word != '<unk>' and not chars:
            word = fix_word(word)
        if word:
            if chars:
                if not first:
                    yield ' '
                else:
                    first = False
                if word == '<unk>':
                    yield word
                else:
                    for c in word:
                        yield c
            else:
                yield word


def get_optimizer(lr, name):
    '''Return an optimizer.'''
    if name == 'sgd':
        optimizer = tf.train.GradientDescentOptimizer(lr)
    elif name == 'adam':
        optimizer = tf.train.AdamOptimizer(lr)
    elif name == 'adagrad':
        optimizer = tf.train.AdagradOptimizer(lr)
    elif name == 'adadelta':
        optimizer = tf.train.AdadeltaOptimizer(lr)
    return optimizer


def list_all_variables(trainable=True, rest=False):
    trainv = tf.trainable_variables()
    if trainable:
        print('\nTrainable:')
        for v in trainv:
            print(v.op.name)
    if rest:
        print('\nOthers:')
        for v in tf.all_variables():
            if v not in trainv:
                print(v.op.name)


def linear(args, output_size, bias, bias_start=0.0, scope=None, train=True, initializer=None):
    """Linear map: sum_i(args[i] * W[i]), where W[i] is a variable.
    Args:
        args: a 2D Tensor or a list of 2D, batch x n, Tensors.
        output_size: int, second dimension of W[i].
        bias: boolean, whether to add a bias term or not.
        bias_start: starting value to initialize the bias; 0 by default.
        scope: VariableScope for the created subgraph; defaults to "Linear".
    Returns:
        A 2D Tensor with shape [batch x output_size] equal to
        sum_i(args[i] * W[i]), where W[i]s are newly created matrices.
    Raises:
        ValueError: if some of the arguments has unspecified or wrong shape.
    Based on the code from TensorFlow."""
    if not tf.nn.nest.is_sequence(args):
        args = [args]

    # Calculate the total size of arguments on dimension 1.
    total_arg_size = 0
    shapes = [a.get_shape().as_list() for a in args]
    for shape in shapes:
        if len(shape) != 2:
            raise ValueError("Linear is expecting 2D arguments: %s" % str(shapes))
        if not shape[1]:
            raise ValueError("Linear expects shape[1] of arguments: %s" % str(shapes))
        else:
            total_arg_size += shape[1]

    dtype = [a.dtype for a in args][0]

    if initializer is None:
        initializer = tf.contrib.layers.xavier_initializer()
    # Now the computation.
    with tf.variable_scope(scope or "Linear"):
        matrix = tf.get_variable("Matrix", [total_arg_size, output_size], dtype=dtype,
                                 initializer=initializer, trainable=train)
        if len(args) == 1:
            res = tf.matmul(args[0], matrix)
        else:
            res = tf.matmul(tf.concat(1, args), matrix)
        if not bias:
            return res
        bias_term = tf.get_variable("Bias", [output_size], dtype=dtype,
                                    initializer=tf.constant_initializer(bias_start, dtype=dtype),
                                    trainable=train)
    return res + bias_term


def highway(input_, layer_size=1, bias=-2, f=tf.nn.tanh, scope=None):
    """Highway Network (cf. http://arxiv.org/abs/1505.00387).
    t = sigmoid(Wy + b)
    z = t * g(Wy + b) + (1 - t) * y
    where g is nonlinearity, t is transform gate, and (1 - t) is carry gate."""
    if tf.nn.nest.is_sequence(input_):
        input_ = tf.concat(1, input_)
    shape = input_.get_shape()
    if len(shape) != 2:
        raise ValueError("Highway is expecting 2D arguments: %s" % str(shape))
    size = shape[1]
    with tf.variable_scope(scope or "Highway"):
        for idx in range(layer_size):
            output = f(linear(input_, size, False, scope='HW_Nonlin_%d' % idx))
            transform_gate = tf.sigmoid(linear(input_, size, False, scope='HW_Gate_%d' % idx)
                                        + bias)
            carry_gate = 1.0 - transform_gate
            output = transform_gate * output + carry_gate * input_
            input_ = output

    return output
