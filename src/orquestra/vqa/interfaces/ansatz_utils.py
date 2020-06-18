from functools import wraps


class _InvalidatingSetter(object):
    """Setter descriptor that sets target object's _circuit and _gratiend_circuits to None.

    The descriptor uses __get__ and __set__ methods. Both of them accept ansatz as a
    first argument (in this case).
    We just forward the __get__, but in __set__ we set obj._circuit to None.
    """

    def __init__(self, target):
        self.target = target

    def __get__(self, ansatz, obj_type):
        return self.target.__get__(ansatz, obj_type)

    def __set__(self, ansatz, new_obj):
        self.target.__set__(ansatz, new_obj)
        ansatz._circuit = None
        ansatz._gradient_circuits = None


def invalidates_circuits(target):
    """Make given target (either property or method) invalidate ansatz's circuit and gradient circuits."""
    if isinstance(target, property):
        # If we are dealing with a property, return our modified descriptor.
        return _InvalidatingSetter(target)
    else:
        # Methods are functions that take instance as a first argument
        # They only change to "bound" methods once the object is instantiated
        # Therefore, we are decorating a function of signature _function(ansatz, ...)
        @wraps(target)
        def _wrapper(ansatz, *args, **kwargs):
            # Pass through the arguments, store the returned value for later use
            return_value = target(ansatz, *args, **kwargs)
            # Invalidate circuit
            ansatz._circuit = None
            ansatz._gradient_circuits = None
            # Return original result
            return return_value

        return _wrapper
