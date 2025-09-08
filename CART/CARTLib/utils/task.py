from CARTLib.core.TaskBaseClass import TaskBaseClass


CART_TASK_REGISTRY: dict[str, type[TaskBaseClass]] = dict()


def cart_task(label: str):
    """
    Class decorator for Tasks we want to register and make available to
    the user. In most cases, the decorated Task class will be registered
    immediately once the file containing it is imported for the first time.

    This initial import is usually done during CART initialization
    (see `initialize_tasks` below), but can be run post-init if needed;
    an example of this is the user selecting a new Task entrypoint through
    the GUI #TODO#
    """
    # Immediate check
    if label in CART_TASK_REGISTRY.keys():
        raise ValueError(f"Cannot register task '{label}'; task with the same "
                         f"name has already been registered with CART.")

    def _register_task(cls: type[TaskBaseClass]):
        if not issubclass(cls, TaskBaseClass):
            raise ValueError(f"Cannot register task '{label}'; task is not a "
                             f"subclass of TaskBaseClass, providing necessary hookups.")

        # If nothing was problematic, add the clas to our registry
        CART_TASK_REGISTRY[label] = cls

        return cls

    return _register_task


def initialize_tasks():
    # Import all example tasks directly
    from CARTLib.examples.MultiContrastSegmentation import MultiContrastSegmentationEvaluationTask
    from CARTLib.examples.RegistrationReview import RegistrationReviewTask

