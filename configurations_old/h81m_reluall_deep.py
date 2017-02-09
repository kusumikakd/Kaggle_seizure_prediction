import lasagne as nn
import theano.tensor as T
from collections import namedtuple
import numpy as np

transformation_params = {
    'highcut': 180,
    'lowcut': 0.1,
    'nfreq_bands': 8,
    'win_length_sec': 60,
    'features': 'meanlog',
    'stride_sec': 60,
    'hours': True
}

l2_reg = 0.0001
max_epochs = 5000
save_every = 10

batch_size = 32
learning_rate_schedule = {0: 0.03, 100: 0.01, 200: 0.003, 300: 0.001, 4000: 0.0001}


def build_model(n_channels, n_fbins, n_timesteps):
    l_in = nn.layers.InputLayer((None, n_channels, n_fbins, n_timesteps))
    lr = nn.layers.ReshapeLayer(l_in, ([0], 1, n_channels * n_fbins, n_timesteps))

    l1c = nn.layers.Conv2DLayer(lr, num_filters=32, filter_size=(n_channels * n_fbins, 1),
                                W=nn.init.Orthogonal('relu'),
                                b=nn.init.Constant(0.1),
                                nonlinearity=nn.nonlinearities.rectify)
    l2c = nn.layers.Conv2DLayer(nn.layers.dropout(l1c, 0.1), num_filters=64, filter_size=(1, 1),
                                W=nn.init.Orthogonal('relu'),
                                b=nn.init.Constant(0.1),
                                nonlinearity=nn.nonlinearities.rectify)

    l3c = nn.layers.Conv2DLayer(nn.layers.dropout(l2c, 0.1), num_filters=64, filter_size=(1, 1),
                                W=nn.init.Orthogonal('relu'),
                                b=nn.init.Constant(0.1),
                                nonlinearity=nn.nonlinearities.rectify)

    l1c_r = nn.layers.DimshuffleLayer(l1c, (0, 3, 1, 2))
    l1c_r = nn.layers.ReshapeLayer(l1c_r, (-1, [2], [3]))
    l_sm1 = nn.layers.DenseLayer(nn.layers.dropout(l1c_r), 2, nonlinearity=nn.nonlinearities.softmax)

    l2c_r = nn.layers.DimshuffleLayer(l2c, (0, 3, 1, 2))
    l2c_r = nn.layers.ReshapeLayer(l2c_r, (-1, [2], [3]))
    l_sm2 = nn.layers.DenseLayer(nn.layers.dropout(l2c_r), 2, nonlinearity=nn.nonlinearities.softmax)

    l3c_r = nn.layers.DimshuffleLayer(l3c, (0, 3, 1, 2))
    l3c_r = nn.layers.ReshapeLayer(l3c_r, (-1, [2], [3]))
    l_sm3 = nn.layers.DenseLayer(nn.layers.dropout(l3c_r), 2, nonlinearity=nn.nonlinearities.softmax)

    lgp_mean = nn.layers.GlobalPoolLayer(l3c, pool_function=T.mean)
    lgp_max = nn.layers.GlobalPoolLayer(l3c, pool_function=T.max)
    lgp_min = nn.layers.GlobalPoolLayer(l3c, pool_function=T.min)
    lgp_var = nn.layers.GlobalPoolLayer(l3c, pool_function=T.var)

    lgp = nn.layers.ConcatLayer([lgp_mean, lgp_max, lgp_min, lgp_var])

    ld = nn.layers.DenseLayer(nn.layers.dropout(lgp), 512, W=nn.init.Orthogonal('relu'),
                              nonlinearity=nn.nonlinearities.rectify)
    ld = nn.layers.DenseLayer(nn.layers.dropout(ld), 512, W=nn.init.Orthogonal('relu'),
                              nonlinearity=nn.nonlinearities.rectify)

    l_out_sm = nn.layers.DenseLayer(nn.layers.dropout(ld), 2, nonlinearity=nn.nonlinearities.softmax,
                                    W=nn.init.Orthogonal())
    l_out = nn.layers.SliceLayer(l_out_sm, indices=1, axis=1)

    l_targets = nn.layers.InputLayer((None,), input_var=T.ivector('tgt'))

    return namedtuple('Model', ['n_timesteps', 'l_in', 'l_out', 'l_targets', 'l_out_sm', 'l_sm1', 'l_sm2', 'l_sm3']) \
        (n_timesteps, l_in, l_out, l_targets, l_out_sm, l_sm1, l_sm2, l_sm3)


def build_objective(model, deterministic=False):
    predictions = nn.layers.get_output(model.l_out_sm, deterministic=deterministic)
    targets = nn.layers.get_output(model.l_targets)
    loss = nn.objectives.categorical_crossentropy(predictions, targets)

    layers = {l: l2_reg for l in nn.layers.get_all_layers(model.l_out)}
    l2_penalty = nn.regularization.regularize_layer_params_weighted(layers, nn.regularization.l2)

    predictions_sm1 = nn.layers.get_output(model.l_sm1, deterministic=deterministic)
    targets_rshp = T.flatten(T.outer(targets, T.ones((model.n_timesteps,), dtype='int32')))
    loss_sm1 = nn.objectives.categorical_crossentropy(predictions_sm1, targets_rshp)

    predictions_sm2 = nn.layers.get_output(model.l_sm2, deterministic=deterministic)
    loss_sm2 = nn.objectives.categorical_crossentropy(predictions_sm2, targets_rshp)

    predictions_sm3 = nn.layers.get_output(model.l_sm3, deterministic=deterministic)
    loss_sm3 = nn.objectives.categorical_crossentropy(predictions_sm3, targets_rshp)

    return T.mean(loss) + T.mean(loss_sm1) + T.mean(loss_sm2) + T.mean(loss_sm3) + l2_penalty


def build_updates(train_loss, model, learning_rate):
    updates = nn.updates.adam(train_loss, nn.layers.get_all_params(model.l_out), learning_rate)
    return updates