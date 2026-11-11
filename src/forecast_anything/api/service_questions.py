"""Question revisions, references, and confirmed operation submissions."""

from uuid import uuid4

from ..contracts import (
    DomainError,
    OperationCreateRequest,
    OperationPage,
    OperationSubmitRequest,
    OperationUpdateRequest,
    OperationView,
    QuestionCreateRequest,
    QuestionPage,
    QuestionReferencePage,
    QuestionReferenceRequest,
    QuestionRevisionPage,
    QuestionRevisionRequest,
    QuestionTitlePatch,
    QuestionView,
)
from ..graph import SourceConfig, parse_node_config


class QuestionOperations:
    def create_question(self, request: QuestionCreateRequest) -> QuestionView:
        return self.ledger.create_question(request)

    def questions(self, *, offset: int, limit: int) -> QuestionPage:
        return self.ledger.list_questions(offset=offset, limit=limit)

    def question(self, question_id: str) -> QuestionView:
        return self.ledger.get_question(question_id)

    def patch_question(
        self, question_id: str, patch: QuestionTitlePatch
    ) -> QuestionView:
        updated = self.ledger.patch_question(question_id, patch)
        references = self.ledger.list_question_references(
            question_id, revision=updated.current_revision, limit=100
        )
        for reference in references.references:
            if reference.target_type != "watch":
                continue
            watch = self.ledger.get_watch(reference.target_id)
            if "status" in patch.model_fields_set:
                if updated.status != "open":
                    other_active = any(
                        link["status"] == "open" and link["question_id"] != question_id
                        for link in self.ledger.question_links_for_watch(watch.watch_id)
                    )
                    if (
                        not other_active
                        and watch.lifecycle != "unsupported"
                        and watch.lifecycle != "paused"
                    ):
                        self.ledger.advance_watch(
                            watch.watch_id,
                            {"kind": "paused"},
                            self.now(),
                            event_id=f"question-pause/{question_id}/{uuid4().hex}",
                        )
                elif watch.lifecycle == "paused":
                    self.ledger.advance_watch(
                        watch.watch_id,
                        {"kind": "resumed"},
                        self.now(),
                        event_id=f"question-resume/{question_id}/{uuid4().hex}",
                    )
            if "priority" in patch.model_fields_set:
                priorities = [
                    link["priority"]
                    for link in self.ledger.question_links_for_watch(watch.watch_id)
                    if link["status"] == "open"
                ]
                priority = min(priorities, default=updated.priority)
                if watch.priority != priority:
                    self.ledger.advance_watch(
                        watch.watch_id,
                        {"kind": "priority_changed", "priority": priority},
                        self.now(),
                        event_id=f"question-priority/{watch.watch_id}/{uuid4().hex}",
                    )
                self.queue.reprioritize_pending_watch(watch.watch_id, priority)
        return updated

    def revise_question(
        self, question_id: str, request: QuestionRevisionRequest
    ) -> QuestionView:
        return self.ledger.revise_question(question_id, request)

    def question_revisions(
        self, question_id: str, *, offset: int, limit: int
    ) -> QuestionRevisionPage:
        return self.ledger.list_question_revisions(
            question_id, offset=offset, limit=limit
        )

    def question_revision(self, question_id: str, revision: int):
        return self.ledger.get_question_revision(question_id, revision)

    def link_question_reference(
        self, question_id: str, request: QuestionReferenceRequest
    ):
        self.ledger.get_question_revision(question_id, request.revision)
        if request.target_type == "candidate":
            self.ledger.get_candidate(request.target_id)
        elif request.target_type == "run":
            self.ledger.get_run(request.target_id)
        elif request.target_type == "watch":
            self.ledger.get_watch(request.target_id)
        elif request.target_type == "evaluation":
            self.ledger.get_evaluation(request.target_id)
        elif request.target_type == "backtest":
            self.backtest(request.target_id)
        elif request.target_type == "operation":
            self.ledger.get_operation(request.target_id)
        return self.ledger.link_question_reference(question_id, request)

    def question_references(
        self, question_id: str, *, revision: int | None, offset: int, limit: int
    ) -> QuestionReferencePage:
        return self.ledger.list_question_references(
            question_id, revision=revision, offset=offset, limit=limit
        )

    def question_presentation(self, question_id: str, *, offset: int, limit: int):
        from ..presentations import present_question

        question = self.ledger.get_question(question_id)
        page = self.ledger.list_question_references(
            question_id, offset=offset, limit=limit
        )
        inbox = self.ledger.list_inbox_events(question_id=question_id, limit=10)
        return present_question(
            question,
            page.references,
            next_offset=page.next_offset,
            inbox_events=inbox.events,
            inbox_total_count=inbox.total_count,
        )

    def create_operation(self, request: OperationCreateRequest) -> OperationView:
        return self.ledger.create_operation(request)

    def operation(self, operation_id: str) -> OperationView:
        return self._operation_view(self.ledger.get_operation(operation_id))

    def operations(
        self, *, question_id: str | None, offset: int, limit: int
    ) -> OperationPage:
        page = self.ledger.list_operations(
            question_id=question_id, offset=offset, limit=limit
        )
        return page.model_copy(
            update={
                "operations": tuple(
                    self._operation_view(item) for item in page.operations
                )
            }
        )

    def update_operation(
        self, operation_id: str, request: OperationUpdateRequest
    ) -> OperationView:
        return self._operation_view(self.ledger.update_operation(operation_id, request))

    def _operation_view(self, view: OperationView) -> OperationView:
        if view.job_id is None:
            return view
        try:
            job = self.job(view.job_id)
        except DomainError as error:
            if error.code == "not_found":
                return view
            raise
        state = {
            "pending": "submitted",
            "running": "submitted",
            "completed": "completed",
            "failed": "failed",
        }.get(job.state, view.state)
        return view.model_copy(
            update={"state": state, "job_state": job.state, "job_error": job.error}
        )

    def _operation_source_ids(self, request: OperationSubmitRequest) -> tuple[str, ...]:
        job = request.request
        if job.kind == "run":
            candidate = self.ledger.get_candidate(request.candidate_id)
            if (
                not candidate.executable
                or candidate.unresolved
                or candidate.graph != job.graph
            ):
                raise DomainError("candidate_not_executable", {})
            declared = {
                config.source_id
                for node in job.graph.nodes
                if node.kind == "source"
                and isinstance((config := parse_node_config(node)), SourceConfig)
            }
            if set(job.snapshot_ids) != declared:
                raise DomainError("invalid_snapshot_bindings", {})
            return ()
        if job.kind == "backtest":
            return (job.source_id,)
        if job.kind == "configured_run":
            return ()
        if job.kind == "evaluation":
            self.ledger.run_bindings(job.run_id)
            return ()
        raise DomainError("invalid_operation_job", {})

    def submit_operation(
        self, operation_id: str, request: OperationSubmitRequest
    ) -> OperationView:
        request = OperationSubmitRequest.model_validate(request.model_dump())
        source_ids = self._operation_source_ids(request)
        self.ledger.reserve_operation_submission(
            operation_id, request, source_ids=source_ids
        )
        stored_view, stored_request = self.ledger.operation_submission(operation_id)
        logical_key = f"operation/{operation_id}"
        if stored_view.job_id is None:
            raise DomainError("operation_job_reservation_missing", {})
        try:
            job = self.queue.get(stored_view.job_id)
            if job.key != logical_key:
                raise DomainError("operation_job_mismatch", {})
        except DomainError as error:
            if error.code != "not_found":
                raise
            accepted = self.submit(stored_request.request, logical_key=logical_key)
            if accepted.job_id != stored_view.job_id:
                raise DomainError("operation_job_mismatch", {}) from None
        self.ledger.mark_operation_enqueued(operation_id, stored_view.job_id)
        return self.operation(operation_id)

    def resume_operation(self, operation_id: str) -> OperationView:
        view, request = self.ledger.operation_submission(operation_id)
        logical_key = f"operation/{operation_id}"
        try:
            job = self.queue.get(view.job_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            return self.submit_operation(operation_id, request)
        if job.key != logical_key:
            raise DomainError("operation_job_mismatch", {})
        self.ledger.mark_operation_enqueued(operation_id, view.job_id)
        return self.operation(operation_id)
