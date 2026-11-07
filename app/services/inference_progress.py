"""Report completed native prediction/encoder batches without changing their outputs."""

from contextlib import contextmanager


def prediction_trainer(model, report, total):
    if report is None:
        return None
    from lab.ner.training.trainer import resolve_trainer_class

    base = resolve_trainer_class(model)

    class ReportingTrainer(base):
        completed = 0

        def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None):
            result = super().prediction_step(model, inputs, prediction_loss_only, ignore_keys)
            if not prediction_loss_only:
                self.completed += int(inputs["input_ids"].shape[0])
                report("INFERENCE", min(total, self.completed), total, "windows")
            return result

    return ReportingTrainer


@contextmanager
def encoder_progress(model, report, stage, total, unit):
    if report is None:
        yield
        return
    completed = 0
    report(stage, 0, total, unit)

    def observed(module, args, kwargs, output):
        nonlocal completed
        inputs = kwargs.get("input_ids", args[0] if args else None)
        if inputs is not None:
            completed += int(inputs.shape[0])
            report(stage, min(total, completed), total, unit)

    hook = model.register_forward_hook(observed, with_kwargs=True)
    try:
        yield
    finally:
        hook.remove()
