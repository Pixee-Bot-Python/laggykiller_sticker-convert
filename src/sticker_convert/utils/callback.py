#!/usr/bin/env python3
from multiprocessing import Event, Queue
from typing import Any, Callable, Dict, Optional, Tuple, Union

from tqdm import tqdm

CbQueueTupleType = Tuple[
    Optional[str], Optional[Tuple[Any, ...]], Optional[Dict[str, Any]]
]
CbQueueItemType = Union[
    CbQueueTupleType,
    str,
    None,
]


class CallbackReturn:
    def __init__(self) -> None:
        self.response_event = Event()
        self.response_queue: Queue[Union[bool, str, None]] = Queue()

    def set_response(self, response: Union[bool, str, None]) -> None:
        self.response_queue.put(response)
        self.response_event.set()

    def get_response(self) -> Union[bool, str, None]:
        self.response_event.wait()

        response = self.response_queue.get()

        self.response_event.clear()

        return response


class Callback:
    def __init__(
        self,
        msg: Optional[Callable[..., None]] = None,
        bar: Optional[Callable[..., None]] = None,
        msg_block: Optional[Callable[..., None]] = None,
        ask_bool: Optional[Callable[..., bool]] = None,
        ask_str: Optional[Callable[..., str]] = None,
        silent: bool = False,
        no_confirm: bool = False,
    ) -> None:
        self.progress_bar: Optional[tqdm[Any]] = None

        if msg:
            self.msg = msg
        else:
            self.msg = self.cb_msg

        if bar:
            self.bar = bar
        else:
            self.bar = self.cb_bar

        if msg_block:
            self.msg_block = msg_block
        else:
            self.msg_block = self.cb_msg_block

        if ask_bool:
            self.ask_bool = ask_bool
        else:
            self.ask_bool = self.cb_ask_bool

        if ask_str:
            self.ask_str = ask_str
        else:
            self.ask_str = self.cb_ask_str

        self.silent = silent
        self.no_confirm = no_confirm

    def cb_msg(self, *args: Any, **kwargs: Any) -> None:
        if self.silent:
            return

        msg = kwargs.get("msg")
        file = kwargs.get("file")

        if not msg and len(args) == 1:
            msg = str(args[0])

        if msg:
            if self.progress_bar:
                self.progress_bar.write(msg)
            elif file:
                print(msg, file=file)
            else:
                print(msg)

    def cb_bar(
        self,
        set_progress_mode: Optional[str] = None,
        steps: int = 0,
        update_bar: bool = False,
    ) -> None:
        if self.silent:
            return

        if self.progress_bar:
            if update_bar:
                self.progress_bar.update()
            elif set_progress_mode == "indeterminate":
                self.progress_bar.close()
                self.progress_bar = None
            elif set_progress_mode == "clear":
                self.progress_bar.reset()
        elif set_progress_mode == "determinate":
            self.progress_bar = tqdm(total=steps)

    def cb_msg_block(self, *args: Any) -> None:
        if self.silent:
            return
        if len(args) > 0:
            msg = " ".join(str(i) for i in args)
            self.msg(msg)
        if not self.no_confirm:
            input("Press Enter to continue...")

    def cb_ask_bool(self, *args: Any, **kwargs: Any) -> bool:
        question = args[0]

        self.msg(question)

        if self.no_confirm:
            self.msg(
                '"--no-confirm" flag is set. Continue with this run without asking questions'
            )
            return True

        self.msg(
            '[If you do not want to get asked by this question, add "--no-confirm" flag]'
        )
        self.msg()
        result = input("Continue? [y/N] > ")
        if result.lower() != "y":
            return False
        return True

    def cb_ask_str(
        self,
        msg: Optional[str] = None,
        initialvalue: Optional[str] = None,
        cli_show_initialvalue: bool = True,
    ) -> str:
        self.msg(msg)

        hint = ""
        if cli_show_initialvalue and initialvalue:
            hint = f" [Default: {initialvalue}]"

        response = input(f"Enter your response and press enter{hint} > ")

        if initialvalue and not response:
            response = initialvalue

        return response

    def put(
        self,
        i: Union[
            CbQueueItemType,
            str,
        ],
    ) -> Union[str, bool, None]:
        if isinstance(i, tuple):
            action = i[0]
            if len(i) >= 2:
                args: Tuple[str, ...] = i[1] if i[1] else tuple()
            else:
                args = tuple()
            if len(i) >= 3:
                kwargs: Dict[str, Any] = i[2] if i[2] else {}
            else:
                kwargs = {}
        else:
            action = i
            args = tuple()
            kwargs = {}

        # Fake implementation for Queue.put()
        if action is None:
            return None
        if action == "msg":
            self.msg(*args, **kwargs)
        elif action == "bar":
            self.bar(**kwargs)
        elif action == "update_bar":
            self.bar(update_bar=True)
        elif action == "msg_block":
            return self.msg_block(*args, **kwargs)
        elif action == "ask_bool":
            return self.ask_bool(*args, **kwargs)
        elif action == "ask_str":
            return self.ask_str(**kwargs)
        else:
            self.msg(action)
        return None
