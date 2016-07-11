"""Conditions and sets of conditions."""

from __future__ import unicode_literals

import logging

from django.utils import six
from django.utils.translation import ugettext as _

from djblets.conditions.errors import (ConditionChoiceNotFoundError,
                                       ConditionOperatorNotFoundError,
                                       InvalidConditionModeError,
                                       InvalidConditionValueError)


class Condition(object):
    """A condition used to match state to a choice, operator, and value.

    Conditions store a choice, operator, and value (depending on the operator).
    Callers can query whether a value fulfills a given condition, making it
    easy for users to compose sets of rules safely for controlling behavior
    in an application without having to write any code.

    Generally, queries will be made against a :py:class:`ConditionSet`, instead
    of an individual Condition.

    Attributes:
        choice (djblets.conditions.choices.BaseConditionChoice):
            The choice stored for this condition.

        operator (djblets.conditions.operators.BaseConditionOperator):
            The operator stored for this condition.

        value (object):
            The value stored for this condition.

        raw_value (object):
            The raw (serialized) value for this condition. This is used
            internally, and won't usually be needed by a caller.
    """

    @classmethod
    def deserialize(cls, choices, data, condition_index=None):
        """Deserialize a condition from serialized data.

        This expects data serialized by :py:meth:`serialize`.

        Args:
            choices (djblets.conditions.choices.ConditionChoices):
                Possible choices for the condition.

            data (dict):
                Serialized data representing this condition.

            condition_index (int, optional):
                The index of the condition within the set of conditions.
                This is used for exceptions to help identify which condition
                failed during deserialization.

        Returns:
            djblets.conditions.conditions.Condition:
            The deserialized condition.

        Raises:
            djblets.conditions.errors.ConditionChoiceNotFoundError:
                The choice ID referenced in the data was missing or did not
                match a valid choice.

            djblets.conditions.errors.ConditionOperatorNotFoundError:
                The operator ID referenced in the data was missing or did not
                match a valid operator for the choice.

            djblets.conditions.errors.InvalidConditionValueError:
                The value was missing from the payload data or was not valid
                for the choice and operator.
        """
        # Sanity-check that we have the data we expect.
        try:
            choice_id = data['choice']
        except KeyError:
            logging.debug('Condition.deserialize: Missing "choice" key for '
                          'condition %r',
                          data)

            raise ConditionChoiceNotFoundError(
                _('A choice is required.'),
                condition_index=condition_index)

        try:
            operator_id = data['op']
        except KeyError:
            logging.debug('Condition.deserialize: Missing "op" key for '
                          'condition %r',
                          data)

            raise ConditionOperatorNotFoundError(
                _('An operator is required.'),
                condition_index=condition_index)

        # Load the choice.
        try:
            choice = choices.get_choice(choice_id)
        except ConditionChoiceNotFoundError as e:
            logging.debug('Condition.deserialize: Invalid "choice" value '
                          '"%s" for condition %r',
                          choice_id, data)

            raise ConditionChoiceNotFoundError(
                six.text_type(e),
                choice_id=choice_id,
                condition_index=condition_index)

        # Load the operator.
        try:
            operator = choice.get_operator(operator_id)
        except ConditionOperatorNotFoundError as e:
            logging.debug('Condition.deserialize: Invalid "op" value "%s" '
                          'for condition %r',
                          operator_id, data)

            raise ConditionOperatorNotFoundError(
                six.text_type(e),
                operator_id=operator_id,
                condition_index=condition_index)

        # Load the value.
        if operator.value_field is not None:
            try:
                raw_value = data['value']
                value = operator.value_field.deserialize_value(raw_value)
            except KeyError:
                logging.debug('Condition.deserialize: Missing "value" value '
                              'for condition %r',
                              data)

                raise InvalidConditionValueError(
                    _('A value is required.'),
                    condition_index=condition_index)
            except InvalidConditionValueError as e:
                logging.debug('Condition.deserialize: Invalid "value" value '
                              '%r for condition %r',
                              raw_value, data)

                e.condition_index = condition_index

                raise
        else:
            raw_value = None
            value = None

        return cls(choice=choice,
                   operator=operator,
                   value=value,
                   raw_value=raw_value)

    def __init__(self, choice, operator, value=None, raw_value=None):
        """Initialize the condition.

        Args:
            choice (djblets.conditions.choices.BaseConditionChoice):
                The choice for this condition.

            operator (djblets.conditions.operators.BaseConditionOperator):
                The operator for this condition.

            value (object, optional):
                The value for this condition.

            raw_value (object, optional):
                The raw (serialized) value for this condition.
        """
        self.choice = choice
        self.operator = operator
        self.value = value

        if raw_value is None:
            self.raw_value = value
        else:
            self.raw_value = raw_value

    def matches(self, value):
        """Return whether a value matches the condition.

        Args:
            value (object):
                The value to match against.

        Returns:
            bool:
            ``True`` if the value fulfills the condition. ``False`` if it
            does not.
        """
        return self.operator.matches(self.choice.get_match_value(value),
                                     self.value)

    def serialize(self):
        """Serialize the condition to a JSON-serializable dictionary.

        Returns:
            dict:
            A dictionary representing the condition. It can be safely
            serialized to JSON.
        """
        data = {
            'choice': self.choice.choice_id,
            'op': self.operator.operator_id,
        }

        if self.operator.value_field is not None:
            if self.value is None:
                value = None
            else:
                value = self.operator.value_field.serialize_value(self.value)

            data['value'] = value

        return data


class ConditionSet(object):
    """A set of conditions used to match state and define rules.

    Condition sets own multiple conditions, and are given a mode indicating
    how to query state against those conditions. They're also responsible
    for serializing and deserializing all data around a set of conditions to
    a JSON-serializable format.

    If using :py:attr:`MODE_ALL`, then all conditions must be satisfied for a
    condition set to pass.  If using :py:attr:`MODE_ANY`, then only one
    condition must be satisfied.

    Attributes:
        mode (unicode):
            The matching mode for the condition set. This is one of
            :py:attr:`MODE_ALL` or :py:attr:`MODE_ANY`.

        conditions (list of Condition):
            The list of conditions that comprise this set.
    """

    #: All conditions must match a value to satisfy the condition set.
    MODE_ALL = 'all'

    #: Any condition may match a value to satisfy the condition set.
    MODE_ANY = 'any'

    @classmethod
    def deserialize(cls, choices, data):
        """Deserialize a set of conditions from serialized data.

        This expects data serialized by :py:meth:`deserialize`.

        Args:
            choices (djblets.conditions.choices.ConditionChoices):
                Possible choices for the condition set.

            data (dict):
                Serialized data representing this condition set.

        Returns:
            djblets.conditions.conditions.ConditionSet:
            The deserialized condition set.

        Raises:
            djblets.conditions.errors.ConditionChoiceNotFoundError:
                The choice ID referenced in the data was missing or did not
                match a valid choice in a condition.

            djblets.conditions.errors.ConditionOperatorNotFoundError:
                The operator ID referenced in the data was missing or did not
                match a valid operator for the choice in a condition.

            djblets.conditions.errors.InvalidConditionValueError:
                The value was missing from the payload data or was not valid
                for the choice and operator in a condition.

            djblets.conditions.errors.InvalidConditionModeError:
                The stored match mode was missing or was not a valid mode.
        """
        mode = data.get('mode')

        if mode not in (cls.MODE_ALL, cls.MODE_ANY):
            logging.debug('ConditionSet.deserialize: Invalid "mode" value '
                          '"%s" for condition set %r',
                          mode, data)

            raise InvalidConditionModeError(
                _('"%s" is not a valid condition mode.')
                % mode)

        return cls(mode, [
            Condition.deserialize(choices, condition_data, i)
            for i, condition_data in enumerate(data.get('conditions', []))
        ])

    def __init__(self, mode=MODE_ALL, conditions=[]):
        """Initialize the condition set.

        Args:
            mode (unicode, optional):
                The match mode. This defaults to :py:attr:`MODE_ALL`.

            conditions (list, optional):
                The conditions that make up this set. This defaults to an
                empty list.

        Raises:
            djblets.conditions.errors.InvalidConditionModeError:
                The match mode is not a valid mode.
        """
        if mode not in (self.MODE_ALL, self.MODE_ANY):
            raise InvalidConditionModeError(
                _('"%s" is not a valid condition mode.')
                % mode)

        self.mode = mode
        self.conditions = conditions

    def matches(self, value):
        """Check if a value matches the condition set.

        Depending on the mode of the condition set, this will either require
        all conditions to match, or only one.

        Args:
            value (object):
                The value to match against.

        Returns:
            bool:
            ``True`` if the value fulfills the condition set. ``False`` if it
            does not.
        """
        if self.mode == self.MODE_ALL:
            match_conditions = all
        elif self.mode == self.MODE_ANY:
            match_conditions = any
        else:
            # We shouldn't be here, unless someone set the mode to a bad value
            # after creating the condition set.
            assert False

        return match_conditions(
            condition.matches(value)
            for condition in self.conditions
        )

    def serialize(self):
        """Serialize the condition set to a JSON-serializable dictionary.

        Returns:
            dict:
            A dictionary representing the condition set. It can be safely
            serialized to JSON.
        """
        return {
            'mode': self.mode,
            'conditions': [
                condition.serialize()
                for condition in self.conditions
            ],
        }