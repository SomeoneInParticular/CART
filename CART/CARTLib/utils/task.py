from CARTLib.core.TaskBaseClass import TaskBaseClass


CART_TASK_REGISTRY: dict[str, type[TaskBaseClass]] = dict()


def initialize_tasks():
    from CARTLib.examples.SegmentationEvaluation.SegmentationEvaluationTask import SegmentationEvaluationTask
    from CARTLib.examples.RegistrationReview.RegistrationReviewTask import RegistrationReviewTask
    from CARTLib.examples.MultiContrastSegmentation.MultiContrastSegmentationEvaluationTask import \
        MultiContrastSegmentationEvaluationTask

    # TODO: Remove this and have them registered via implicit decorator
    example_map = {
        "Segmentation": SegmentationEvaluationTask,
        "MultiContrast Segmentation": MultiContrastSegmentationEvaluationTask,
        "Registration Review": RegistrationReviewTask,
    }

    CART_TASK_REGISTRY.update(example_map)
