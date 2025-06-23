from abc import ABC, abstractmethod
from typing import Any, List, Dict
import logging
import time
from src.manager import StateManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PipelineContext:
    def __init__(self, input_data: Any):
        self.input_data = input_data
        self.results = {}
        self.errors = []
        self.metadata = {}

    def set_result(self, step_name: str, result: Any):
        self.results[step_name] = result

    def get_result(self, step_name: str) -> Any:
        return self.results.get(step_name)

    def add_error(self, step_name: str, error: Exception):
        self.errors.append((step_name, error))
        logger.error(f"Error in {step_name}: {str(error)}")

class ProcessingStep(ABC):
    @abstractmethod
    def process(self, context: PipelineContext, config: Dict, state_manager: StateManager) -> PipelineContext:
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__

class Pipeline:
    def __init__(self, steps: List[ProcessingStep], config: Dict, state_manager: StateManager, continue_on_error: bool = None):
        self.steps = steps
        self.config = config
        self.state_manager = state_manager
        self.continue_on_error = continue_on_error if continue_on_error is not None else config["pipeline"].get("continue_on_error", False)
        self.failed_step = None

    def run(self, input_data: Any, context: PipelineContext = None) -> PipelineContext:
        input_type = self.config["pipeline"]["input_type"]
        if context is None:
            context = PipelineContext(input_data)
        context.metadata["id"] = self.state_manager.get_index(input_data, input_type)  # Global unique ID
        context.metadata["input_type"] = input_type
        total_start_time = time.time()

        for i, step in enumerate(self.steps, start=1):
            step_output = self.state_manager.get_step_output(input_data, input_type, context.metadata["id"], step.name)
            if step_output and not self.config["pipeline"].get("force_reprocess", False):
                logger.info(f"STEP {i}/{len(self.steps)}: {step.name} skipped (output exists at [{step_output}])")
                context.set_result(step.name, step_output)
                continue
            try:
                start_time = time.time()
                logger.info(f"Step {i}/{len(self.steps)}: {step.name} processing...")
                context = step.process(context, self.config, self.state_manager)
                if context.get_result(step.name):
                    self.state_manager.save_step_output(
                        context.input_data,
                        input_type,
                        context.metadata["id"],
                        step.name,
                        context.get_result(step.name)
                    )
                end_time = time.time()
                logger.info(f"Step {i}/{len(self.steps)}: {step.name} done in [{end_time - start_time:.2f} seconds]")
            except Exception as e:
                self.failed_step = step.name
                context.add_error(step.name, e)
                self.state_manager.log_error(context.input_data, input_type, context.metadata["id"], step.name, str(e))
                if self.continue_on_error:
                    logger.warning(f"Continuing after error in {step.name}")
                    continue
                raise

        total_end_time = time.time()
        logger.info(f"Total pipeline runtime: {total_end_time - total_start_time:.2f} seconds")
        return context

    def run_batch(self, inputs: List[Any]) -> List[PipelineContext]:
        results = []
        total_start_time = time.time()
        input_type = self.config["pipeline"]["input_type"]
        for i, input_data in enumerate(inputs, 1):
            try:
                logger.info(f"###### Processing input {i}/{len(inputs)}: {input_data} ######")
                context = self.run(input_data)
                results.append(context)
            except Exception as e:
                self.failed_step = "Batch"
                logger.error(f"Failed to process input {input_data}: {str(e)}")
                self.state_manager.log_error(input_data, input_type, context.metadata["id"] if 'context' in locals() else i, "Batch", str(e))
                if self.continue_on_error:
                    continue
                raise
        total_end_time = time.time()
        logger.info(f"Total batch runtime: {total_end_time - total_start_time:.2f} seconds")
        return results

    def get_failed_step(self) -> str:
        return self.failed_step