from __future__ import division

import sys
import time

import numpy as np
import tensorflow as tf

from config import Config
from encdec import EncoderDecoderModel
from reader import Reader, Vocab


def call_session(session, model, batch):
    '''Use the session to run the model on the batch data.'''
    f_dict = {model.ldata: batch[0], model.rdata: batch[1], model.lengths: batch[2]}
    # model.train_op will be tf.no_op() for a non-training model
    ret = session.run([model.nll, model.mle_cost, model.gan_cost, model.train_op], f_dict)
    return ret[:-1]


def save_model(session, saver, config, perp, cur_iters):
    '''Save model file.'''
    save_file = config.save_file
    if not config.save_overwrite:
        save_file = save_file + '.' + str(cur_iters)
    print "Saving model (epoch perplexity: %.3f) ..." % perp
    save_file = saver.save(session, save_file)
    print "Saved to", save_file


def run_epoch(session, mle_model, gan_model, batch_loader, config, vocab, saver, steps, max_steps):
    '''Runs the model on the given data for an epoch.'''
    start_time = time.time()
    nlls = 0.0
    mle_costs = 0.0
    gan_costs = 0.0
    iters = 0
    shortterm_nlls = 0.0
    shortterm_mle_costs = 0.0
    shortterm_gan_costs = 0.0
    shortterm_iters = 0

    for step, batch in enumerate(batch_loader):
        nll, mle_cost, gan_cost = call_session(session, mle_model, batch) # TODO GAN updates?

        nlls += nll
        mle_costs += mle_cost
        gan_costs += gan_cost
        shortterm_nlls += nll
        shortterm_mle_costs += mle_cost
        shortterm_gan_costs += gan_cost
        # batch[1] is the right aligned batch, without <eos>. predictions also have one token less.
        iters += batch[1].shape[1]
        shortterm_iters += batch[1].shape[1]

        if step % config.print_every == 0:
            avg_nll = shortterm_nlls / shortterm_iters
            avg_mle_cost = shortterm_mle_costs / shortterm_iters
            avg_gan_cost = shortterm_gan_costs / shortterm_iters
            print("%d  perplexity: %.3f  mle_loss: %.4f  mle_cost: %.4f  gan_cost: %.4f  "
                  "speed: %.0f wps" %
                  (step, np.exp(avg_nll), avg_nll, avg_mle_cost, avg_gan_cost,
                   shortterm_iters * config.batch_size / (time.time() - start_time)))

            shortterm_nlls = 0.0
            shortterm_mle_costs = 0.0
            shortterm_gan_costs = 0.0
            shortterm_iters = 0
            start_time = time.time()

        cur_iters = steps + step
        if saver is not None and cur_iters and config.save_every > 0 and \
                cur_iters % config.save_every == 0:
            save_model(session, saver, config, np.exp(nlls / iters), cur_iters)

        if max_steps > 0 and cur_iters >= max_steps:
            break

    perp = np.exp(nlls / iters)
    cur_iters = steps + step
    if saver is not None and config.save_every < 0:
        save_model(session, saver, config, perp, cur_iters)
    return perp, cur_iters


def main(_):
    config = Config()
    vocab = Vocab(config)
    vocab.load_from_pickle()
    reader = Reader(config, vocab)

    config_proto = tf.ConfigProto()
    config_proto.gpu_options.allow_growth = True
    with tf.Graph().as_default(), tf.Session(config=config_proto) as session:
        if config.training:
            with tf.variable_scope("Model", reuse=None):
                mle_model = EncoderDecoderModel(config, vocab, True, True)
                gan_model = EncoderDecoderModel(config, vocab, True, False)
            with tf.variable_scope("Model", reuse=True):
                eval_model = EncoderDecoderModel(config, vocab, False, True)
        else:
            with tf.variable_scope("Model", reuse=None):
                test_model = EncoderDecoderModel(config, vocab, False, True)
        saver = tf.train.Saver()
        try:
            # try to restore a saved model file
            saver.restore(session, config.load_file)
            print "Model restored from", config.load_file
        except ValueError:
            if config.training:
                tf.initialize_all_variables().run()
                print "No loadable model file, new model initialized."
            else:
                print "You need to provide a valid model file for testing!"
                sys.exit(1)

        if config.training:
            steps = 0
            train_perps = []
            valid_perps = []
            mle_model.assign_lr(session, config.learning_rate)
            gan_model.assign_d_lr(session, config.learning_rate) # TODO different learning rates
            gan_model.assign_g_lr(session, config.learning_rate) # TODO ^
            for i in xrange(config.max_epoch):
                print "\nEpoch: %d MLE learning rate: %.4f, D learning rate: %.4f, " \
                      "G learning rate: %.4f" % (i + 1, session.run(mle_model.mle_lr),
                                           session.run(gan_model.d_lr), session.run(gan_model.g_lr))
                perplexity, steps = run_epoch(session, mle_model, gan_model, reader.training(),
                                              config, vocab, saver, steps, config.max_steps)
                print "Epoch: %d Train Perplexity: %.3f" % (i + 1, perplexity)
                train_perps.append(perplexity)
                if config.validate_every > 0 and (i + 1) % config.validate_every == 0:
                    perplexity, _ = run_epoch(session, eval_model, None, reader.validation(),
                                              config, vocab, None, 0, -1)
                    print "Epoch: %d Validation Perplexity: %.3f" % (i + 1, perplexity)
                    valid_perps.append(perplexity)
                else:
                    valid_perps.append(None)
                print 'Train:', train_perps
                print 'Valid:', valid_perps
                if steps >= config.max_steps:
                    break
        else:
            print '\nTesting'
            perplexity, _ = run_epoch(session, test_model, None, reader.testing(), config, vocab,
                                      None, 0, config.max_steps)
            print "Test Perplexity: %.3f" % perplexity


if __name__ == "__main__":
    tf.app.run()
