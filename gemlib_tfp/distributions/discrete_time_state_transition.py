"""Describes a DiscreteTimeStateTransitionModel"""
import numpy as np
import tensorflow as tf
import tensorflow_probability as tfp
from tensorflow_probability.python.internal import dtype_util
from tensorflow_probability.python.internal import reparameterization

from gemlib_tfp.distributions.impl.util import batch_gather, transition_coords

from gemlib_tfp.distributions.impl.discrete_markov import (
    discrete_markov_simulation,
    discrete_markov_log_prob,
)

tla = tf.linalg
tfd = tfp.distributions


__all__ = ["DiscreteTimeStateTransitionModel"]


class DiscreteTimeStateTransitionModel(tfd.Distribution):
    def __init__(
        self,
        transition_rates,
        stoichiometry,
        initial_state,
        initial_step,
        time_delta,
        num_steps,
        validate_args=False,
        allow_nan_stats=True,
        name="DiscreteTimeStateTransitionModel",
    ):
        """Implements a discrete-time Markov jump process for a state transition model.

        :param transition_rates: a function of the form `fn(t, state)` taking
               the current time `t` and state tensor `state`.  This function
               returns a tensor which broadcasts to the first dimension of
               `stoichiometry`.
        :param stoichiometry: the stochiometry matrix for the state transition model,
               with rows representing transitions and columns representing states.
        :param initial_state: an initial state tensor with inner dimension equal to the
               first dimension of `stoichiometry`.
        :param initial_step: an offset giving the time `t` of the first timestep in the
               model.
        :param time_delta: the size of the time step to be used.
        :param num_steps: the number of time steps across which the model runs.
        """

        parameters = dict(locals())
        with tf.name_scope(name) as name:
            self._transition_rates = transition_rates
            self._initial_state = tf.convert_to_tensor(initial_state)
            self._dtype = self._initial_state.dtype
            self._stoichiometry = np.array(stoichiometry, dtype=self._dtype)
            self._initial_step = tf.convert_to_tensor(initial_step)
            self._time_delta = tf.convert_to_tensor(time_delta)
            self._num_steps = num_steps

            super().__init__(
                dtype=initial_state.dtype,
                reparameterization_type=reparameterization.FULLY_REPARAMETERIZED,
                validate_args=validate_args,
                allow_nan_stats=allow_nan_stats,
                parameters=parameters,
                name=name,
            )

        self.dtype = initial_state.dtype

    @property
    def transition_rates(self):
        return self._transition_rates

    @property
    def stoichiometry(self):
        return self._stoichiometry

    @property
    def initial_state(self):
        return self._initial_state

    @property
    def initial_step(self):
        return self._initial_step

    @property
    def time_delta(self):
        return self._time_delta

    @property
    def num_steps(self):
        return self._num_steps

    def _batch_shape(self):
        return tf.TensorShape([])

    def _event_shape(self):
        shape = tf.TensorShape(
            [
                self.initial_state.shape[0],
                tf.get_static_value(self._num_steps),
                self._stoichiometry.shape[0],
            ]
        )
        return shape

    def _sample_n(self, n, seed=None):
        """Runs a simulation from the epidemic model

        :param param: a dictionary of model parameters
        :param state_init: the initial state
        :returns: a tuple of times and simulated states.
        """
        with tf.name_scope("DiscreteTimeStateTransitionModel.log_prob"):
            t, sim = discrete_markov_simulation(
                hazard_fn=self.transition_rates,
                state=self.initial_state,
                start=self.initial_step,
                end=self.initial_step + self.num_steps * self.time_delta,
                time_step=self.time_delta,
                stoichiometry=self.stoichiometry,
                seed=seed,
            )
            indices = transition_coords(self.stoichiometry)
            sim = batch_gather(sim, indices)
            sim = tf.transpose(sim, perm=(1, 0, 2))
            return tf.expand_dims(sim, 0)

    def _log_prob(self, y, **kwargs):
        """Calculates the log probability of observing epidemic events y
        :param y: a list of tensors.  The first is of shape [n_times] containing times,
                  the second is of shape [n_times, n_states, n_states] containing event matrices.
        :param param: a list of parameters
        :returns: a scalar giving the log probability of the epidemic
        """
        dtype = dtype_util.common_dtype(
            [y, self.initial_state], dtype_hint=self._dtype
        )
        y = tf.convert_to_tensor(y, dtype)
        with tf.name_scope("CovidUKStochastic.log_prob"):
            hazard = self.transition_rates
            return discrete_markov_log_prob(
                events=y,
                init_state=self.initial_state,
                init_step=self.initial_step,
                time_delta=self.time_delta,
                hazard_fn=hazard,
                stoichiometry=self.stoichiometry,
            )
