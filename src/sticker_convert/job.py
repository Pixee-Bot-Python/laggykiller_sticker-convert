#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from multiprocessing import Process, Value
from multiprocessing.managers import BaseProxy, SyncManager
from pathlib import Path
from threading import Thread
from typing import Optional, Callable, Union
from urllib.parse import urlparse

from sticker_convert.converter import StickerConvert  # type: ignore
from sticker_convert.definitions import ROOT_DIR  # type: ignore
from sticker_convert.downloaders.download_kakao import DownloadKakao  # type: ignore
from sticker_convert.downloaders.download_line import DownloadLine  # type: ignore
from sticker_convert.downloaders.download_signal import DownloadSignal  # type: ignore
from sticker_convert.downloaders.download_telegram import DownloadTelegram  # type: ignore
from sticker_convert.job_option import (CompOption, CredOption,  # type: ignore
                                        InputOption, OutputOption)
from sticker_convert.uploaders.compress_wastickers import CompressWastickers  # type: ignore
from sticker_convert.uploaders.upload_base import UploadBase
from sticker_convert.uploaders.upload_signal import UploadSignal  # type: ignore
from sticker_convert.uploaders.upload_telegram import UploadTelegram  # type: ignore
from sticker_convert.uploaders.xcode_imessage import XcodeImessage  # type: ignore
from sticker_convert.utils.callback import CallbackReturn  # type: ignore
from sticker_convert.utils.files.json_manager import JsonManager  # type: ignore
from sticker_convert.utils.files.metadata_handler import MetadataHandler  # type: ignore
from sticker_convert.utils.media.codec_info import CodecInfo  # type: ignore

work_queue_type: BaseProxy[Optional[tuple]]
results_queue_type: BaseProxy[
    Union[
        tuple[
            Optional[str],
            Optional[tuple],
            Optional[dict]],
        str,
        None
        ]
    ]
cb_queue_type: BaseProxy[Optional[tuple[str, tuple]]]

class Executor:
    def __init__(self,
                cb_msg: Callable,
                cb_msg_block: Callable,
                cb_bar: Callable,
                cb_ask_bool: Callable,
                cb_ask_str: Callable):
        
        self.cb_msg = cb_msg
        self.cb_msg_block = cb_msg_block
        self.cb_bar = cb_bar
        self.cb_ask_bool = cb_ask_bool
        self.cb_ask_str = cb_ask_str
        
        self.manager = SyncManager()
        self.manager.start()
        self.work_queue: work_queue_type = self.manager.Queue()
        self.results_queue: results_queue_type = self.manager.Queue()
        self.cb_queue: cb_queue_type = self.manager.Queue()
        self.cb_return = CallbackReturn()
        self.processes: list[Process] = []

        self.is_cancel_job = Value('i', 0)

    def cb_thread(
            self,
            cb_queue: work_queue_type,
            cb_return: CallbackReturn
            ):
        for i in iter(cb_queue.get, None): # type: ignore[misc]
            if isinstance(i, tuple):
                action = i[0]
                if len(i) >= 2:
                    args = i[1] if i[1] else tuple()
                else:
                    args = tuple()
                if len(i) >= 3:
                    kwargs = i[2] if i[2] else dict()
                else:
                    kwargs = dict()
            else:
                action = i
                args = tuple()
                kwargs = dict()
            if action == "msg":
                self.cb_msg(*args, **kwargs)
            elif action == "bar":
                self.cb_bar(*args, **kwargs)
            elif action == "update_bar":
                self.cb_bar(update_bar=True)
            elif action == "msg_block":
                cb_return.set_response(self.cb_msg_block(*args, **kwargs))
            elif action == "ask_bool":
                cb_return.set_response(self.cb_ask_bool(*args, **kwargs))
            elif action == "ask_str":
                cb_return.set_response(self.cb_ask_str(*args, **kwargs))
            else:
                self.cb_msg(action)

    @staticmethod
    def worker(
        work_queue: work_queue_type, 
        results_queue: results_queue_type, 
        cb_queue: cb_queue_type,
        cb_return: CallbackReturn
        ):

        for work_func, work_args in iter(work_queue.get, None):
            try:
                results = work_func(*work_args, cb_queue, cb_return) # type: ignore
                results_queue.put(results)
            except Exception:
                e = '##### EXCEPTION #####\n'
                e += 'Function: ' + repr(work_func) + '\n'
                e += 'Arguments: ' + repr(work_args) + '\n'
                e += traceback.format_exc()
                e += '#####################'
                cb_queue.put(e)
        work_queue.put(None)

    def start_workers(self, processes: int = 1):
        # Would contain None from previous run
        while not self.work_queue.empty():
            self.work_queue.get()

        Thread(target=self.cb_thread, args=(self.cb_queue, self.cb_return,)).start()

        for _ in range(processes):
            process = Process(
                target=Executor.worker,
                args=(self.work_queue, self.results_queue, self.cb_queue, self.cb_return),
                daemon=True
            )

            process.start()
            self.processes.append(process)

    def add_work(self, work_func: Callable, work_args: tuple):
        self.work_queue.put((work_func, work_args))

    def join_workers(self):
        self.work_queue.put(None)
        try:
            for process in self.processes:
                process.join()
        except KeyboardInterrupt:
            pass
        
        self.results_queue.put(None)

        self.process = []

    def kill_workers(self, *args, **kwargs):
        self.is_cancel_job.value = 1
        while not self.work_queue.empty():
            self.work_queue.get()

        for process in self.processes:
            process.terminate()
            process.join()
        
        self.cleanup()
    
    def cleanup(self):
        self.cb_queue.put(None)

    def get_result(self) -> tuple:
        for result in iter(self.results_queue.get, None):
            yield result
    
    def cb(self, action: Optional[str], args: Optional[tuple] = None, kwargs: Optional[dict] = None):
        self.cb_queue.put((action, args, kwargs))


class Job:
    def __init__(self,
        opt_input: InputOption, opt_comp: CompOption,
        opt_output: OutputOption, opt_cred: CredOption, 
        cb_msg: Callable,
        cb_msg_block: Callable,
        cb_bar: Callable,
        cb_ask_bool: Callable,
        cb_ask_str: Callable):

        self.opt_input = opt_input
        self.opt_comp = opt_comp
        self.opt_output = opt_output
        self.opt_cred = opt_cred
        self.cb_msg = cb_msg
        self.cb_msg_block = cb_msg_block
        self.cb_bar = cb_bar
        self.cb_ask_bool = cb_ask_bool
        self.cb_ask_str = cb_ask_str

        self.compress_fails: list[str] = []
        self.out_urls: list[str] = []

        self.executor = Executor(
            self.cb_msg,
            self.cb_msg_block,
            self.cb_bar,
            self.cb_ask_bool,
            self.cb_ask_str
        )

    def start(self) -> bool:
        if Path(self.opt_input.dir).is_dir() == False:
            os.makedirs(self.opt_input.dir)

        if Path(self.opt_output.dir).is_dir() == False:
            os.makedirs(self.opt_output.dir)
            
        self.executor.cb("msg", kwargs={"cls": True})

        tasks = (
            self.verify_input,
            self.cleanup,
            self.download,
            self.compress,
            self.export,
            self.report
        )

        code = 0
        for task in tasks:
            self.executor.cb("bar", kwargs={"set_progress_mode": "indeterminate"})
            success = task()

            if self.executor.is_cancel_job.value == 1:
                code = 2
                self.executor.cb('Job cancelled.')
                break
            elif not success:
                code = 1
                self.executor.cb('An error occured during this run.')
                break

        self.executor.cb("bar", kwargs={"set_progress_mode": 'clear'})

        return code

    def cancel(self):
        self.executor.kill_workers()

    def verify_input(self) -> bool:
        info_msg = ''
        error_msg = ''

        save_to_local_tip = ''
        save_to_local_tip += '    If you want to upload the results by yourself,\n'
        save_to_local_tip += '    select "Save to local directory only" for output\n'

        if Path(self.opt_input.dir).resolve() == Path(self.opt_output.dir).resolve():
            error_msg += '\n'
            error_msg += '[X] Input and output directories cannot be the same\n'

        if self.opt_input.option == 'auto':
            error_msg += '\n'
            error_msg += '[X] Unrecognized URL input source\n'

        if (self.opt_input.option != 'local' and 
            not self.opt_input.url):

            error_msg += '\n'
            error_msg += '[X] URL address cannot be empty.\n'
            error_msg += '    If you only want to use local files,\n'
            error_msg += '    choose "Save to local directory only"\n'
            error_msg += '    in "Input source"\n'
        

        if ((self.opt_input.option == 'telegram' or 
            self.opt_output.option == 'telegram') and 
            not self.opt_cred.telegram_token):

            error_msg += '[X] Downloading from and uploading to telegram requires bot token.\n'
            error_msg += save_to_local_tip

        if (self.opt_output.option == 'telegram' and 
            not self.opt_cred.telegram_userid):

            error_msg += '[X] Uploading to telegram requires user_id \n'
            error_msg += '    (From real account, not bot account).\n'
            error_msg += save_to_local_tip
        

        if (self.opt_output.option == 'signal' and 
            not (self.opt_cred.signal_uuid and self.opt_cred.signal_password)):

            error_msg += '[X] Uploading to signal requires uuid and password.\n'
            error_msg += save_to_local_tip
        
        output_presets = JsonManager.load_json(ROOT_DIR / 'resources/output.json')

        input_option = self.opt_input.option
        output_option = self.opt_output.option
        
        for metadata in ('title', 'author'):
            if MetadataHandler.check_metadata_required(output_option, metadata) and not getattr(self.opt_output, metadata):
                if not MetadataHandler.check_metadata_provided(self.opt_input.dir, input_option, metadata):
                    error_msg += f'[X] {output_presets[output_option]["full_name"]} requires {metadata}\n'
                    if self.opt_input.option == 'local':
                        error_msg += f'    {metadata} was not supplied and {metadata}.txt is absent\n'
                    else:
                        error_msg += f'    {metadata} was not supplied and input source will not provide {metadata}\n'
                    error_msg += f'    Supply the {metadata} by filling in the option, or\n'
                    error_msg += f'    Create {metadata}.txt with the {metadata} name\n'
                else:
                    info_msg += f'[!] {output_presets[output_option]["full_name"]} requires {metadata}\n'
                    if self.opt_input.option == 'local':
                        info_msg += f'    {metadata} was not supplied but {metadata}.txt is present\n'
                        info_msg += f'    Using {metadata} name in {metadata}.txt\n'
                    else:
                        info_msg += f'    {metadata} was not supplied but input source will provide {metadata}\n'
                        info_msg += f'    Using {metadata} provided by input source\n'
        
        if info_msg != '':
            self.executor.cb(info_msg)

        if error_msg != '':
            self.executor.cb(error_msg)
            return False
        
        # Check if preset not equal to export option
        # Only warn if the compression option is available in export preset
        # Only warn if export option is not local or custom
        # Do not warn if no_compress is true
        if (not self.opt_comp.no_compress and 
            self.opt_output.option != 'local' and
            self.opt_comp.preset != 'custom' and
            self.opt_output.option not in self.opt_comp.preset):

            msg = 'Compression preset does not match export option\n'
            msg += 'You may continue, but the files will need to be compressed again before export\n'
            msg += 'You are recommended to choose the matching option for compression and output. Continue?'

            response = self.executor.cb("ask_bool", (msg,))

            if response == False:
                return False
        
        for param, value in (
            ('fps_power', self.opt_comp.fps_power),
            ('res_power', self.opt_comp.res_power),
            ('quality_power', self.opt_comp.quality_power),
            ('color_power', self.opt_comp.color_power)
        ):
            if value < -1:
                error_msg += '\n'
                error_msg += f'[X] {param} should be between -1 and positive infinity. {value} was given.'
        
        if self.opt_comp.scale_filter not in ('nearest', 'bilinear', 'bicubic', 'lanczos'):
            error_msg += '\n'
            error_msg += f'[X] scale_filter {self.opt_comp.scale_filter} is not valid option'
            error_msg += '    Valid options: nearest, bilinear, bicubic, lanczos'

        if self.opt_comp.quantize_method not in ('imagequant', 'fastoctree', 'none'):
            error_msg += '\n'
            error_msg += f'[X] quantize_method {self.opt_comp.quantize_method} is not valid option'
            error_msg += '    Valid options: imagequant, fastoctree, none'
        
        # Warn about unable to download animated Kakao stickers with such link
        if (self.opt_output.option == 'kakao' and 
            urlparse(self.opt_input.url).netloc == 'e.kakao.com' and
            not self.opt_cred.kakao_auth_token):

            msg = 'To download ANIMATED stickers from e.kakao.com,\n'
            msg += 'you need to generate auth_token.\n'
            msg += 'Alternatively, you can generate share link (emoticon.kakao.com/items/xxxxx)\n'
            msg += 'from Kakao app on phone.\n'
            msg += 'You are adviced to read documentations.\n'
            msg += 'If you continue, you will only download static stickers. Continue?'

            response = self.executor.cb("ask_bool", (msg,))

            if response == False:
                return False
            
            response = self.executor.cb("ask_bool", (msg,))

            if response == False:
                return False
        
        return True

    def cleanup(self) -> bool:
        # If input is 'From local directory', then we should keep files in input/output directory as it maybe edited by user
        # If input is not 'From local directory', then we should move files in input/output directory as new files will be downloaded
        # Output directory should be cleanup unless no_compress is true (meaning files in output directory might be edited by user)

        timestamp = datetime.now().strftime('%Y-%d-%m_%H-%M-%S')
        dir_name = 'archive_' + timestamp

        in_dir_files = [i for i in os.listdir(self.opt_input.dir) if not i.startswith('archive_')]
        out_dir_files = [i for i in os.listdir(self.opt_output.dir) if not i.startswith('archive_')]

        if self.opt_input.option == 'local':
            self.executor.cb('Skip moving old files in input directory as input source is local')
        elif len(in_dir_files) == 0:
            self.executor.cb('Skip moving old files in input directory as input source is empty')
        else:
            archive_dir = Path(self.opt_input.dir, dir_name)
            self.executor.cb(f"Moving old files in input directory to {archive_dir} as input source is not local")
            os.makedirs(archive_dir)
            for i in in_dir_files:
                old_path = Path(self.opt_input.dir, i)
                new_path = archive_dir / i
                shutil.move(old_path, new_path)

        if self.opt_comp.no_compress:
            self.executor.cb('Skip moving old files in output directory as no_compress is True')
        elif len(out_dir_files) == 0:
            self.executor.cb('Skip moving old files in output directory as output source is empty')
        else:
            archive_dir = Path(self.opt_output.dir, dir_name)
            self.executor.cb(f"Moving old files in output directory to {archive_dir}")
            os.makedirs(archive_dir)
            for i in out_dir_files:
                old_path = Path(self.opt_output.dir, i)
                new_path = archive_dir / i
                shutil.move(old_path, new_path)
        
        return True

    def download(self) -> bool:
        downloaders = []

        if self.opt_input.option == 'signal':
            downloaders.append(DownloadSignal.start)

        if self.opt_input.option == 'line':
            downloaders.append(DownloadLine.start)
            
        if self.opt_input.option == 'telegram':
            downloaders.append(DownloadTelegram.start)

        if self.opt_input.option == 'kakao':
            downloaders.append(DownloadKakao.start)
        
        if len(downloaders) > 0:
            self.executor.cb('Downloading...')
        else:
            self.executor.cb('Nothing to download')
            return True
        
        self.executor.start_workers(processes=1)

        for downloader in downloaders:
            self.executor.add_work(
                work_func=downloader,
                work_args=(
                    self.opt_input.url, 
                    self.opt_input.dir, 
                    self.opt_cred
                )
            )
        
        self.executor.join_workers()

        # Return False if any of the job returns failure
        for result in self.executor.get_result():
            if result == False:
                return False

        self.executor.cleanup()

        return True

    def compress(self) -> bool:
        if self.opt_comp.no_compress == True:
            self.executor.cb('no_compress is set to True, skip compression')
            in_dir_files = [i for i in sorted(os.listdir(self.opt_input.dir)) if Path(self.opt_input.dir, i).is_file()]
            out_dir_files = [i for i in sorted(os.listdir(self.opt_output.dir)) if Path(self.opt_output.dir, i).is_file()]
            if len(in_dir_files) == 0:
                self.executor.cb('Input directory is empty, nothing to copy to output directory')
            elif len(out_dir_files) != 0:
                self.executor.cb('Output directory is not empty, not copying files from input directory')
            else:
                self.executor.cb('Output directory is empty, copying files from input directory')
                for i in in_dir_files:
                    src_f = Path(self.opt_input.dir, i)
                    dst_f = Path(self.opt_output.dir, i)
                    shutil.copy(src_f, dst_f)
            return True
        msg = 'Compressing...'

        input_dir = Path(self.opt_input.dir)
        output_dir = Path(self.opt_output.dir)
        
        in_fs = []

        # .txt: emoji.txt, title.txt
        # .m4a: line sticker sound effects
        for i in sorted(os.listdir(input_dir)):
            in_f = input_dir / i
            
            if not in_f.is_file():
                continue
            elif (CodecInfo.get_file_ext(i) in ('.txt', '.m4a') or
                  Path(i).stem == 'cover'):
                
                shutil.copy(in_f, output_dir / i)
            else:
                in_fs.append(i)

        in_fs_count = len(in_fs)

        self.executor.cb(msg)
        self.executor.cb("bar", kwargs={'set_progress_mode': 'determinate', 'steps': in_fs_count})

        self.executor.start_workers(processes=min(self.opt_comp.processes, in_fs_count))

        for i in in_fs:
            in_f = input_dir / i
            out_f = output_dir / Path(i).stem

            self.executor.add_work(
                work_func=StickerConvert.convert,
                work_args=(in_f, out_f, self.opt_comp)
            )

        self.executor.join_workers()

        # Return False if any of the job returns failure
        for result in self.executor.get_result():
            if result[0] == False:
                return False
        
        return True

    def export(self) -> bool:
        if self.opt_output.option == 'local':
            self.executor.cb('Saving to local directory only, nothing to export')
            return True
        
        self.executor.cb('Exporting...')

        exporters: list[UploadBase] = []

        if self.opt_output.option == 'whatsapp':
            exporters.append(CompressWastickers.start)

        if self.opt_output.option == 'signal':
            exporters.append(UploadSignal.start)

        if self.opt_output.option == 'telegram':
            exporters.append(UploadTelegram.start)
        
        if self.opt_output.option == 'telegram_emoji':
            exporters.append(UploadTelegram.start)

        if self.opt_output.option == 'imessage':
            exporters.append(XcodeImessage.start)

        self.executor.start_workers(processes=1)

        for exporter in exporters:
            self.executor.add_work(
                work_func=exporter,
                work_args=(
                    self.opt_output, 
                    self.opt_comp, 
                    self.opt_cred
                )
            )

        self.executor.join_workers()

        for result in self.executor.get_result():
            self.out_urls.extend(result)

        if self.out_urls:
            with open(Path(self.opt_output.dir, 'export-result.txt'), 'w+') as f:
                f.write('\n'.join(self.out_urls))
        else:
            self.executor.cb('An error occured while exporting stickers')
            return False
        
        return True
    
    def report(self) -> bool:
        msg = '##########\n'
        msg += 'Summary:\n'
        msg += '##########\n'
        msg += '\n'

        if self.compress_fails != []:
            msg += f'Warning: Could not compress the following {len(self.compress_fails)} file{"s" if len(self.compress_fails) > 1 else ""}:\n'
            msg += "\n".join(self.compress_fails)
            msg += '\n'
            msg += '\nConsider adjusting compression parameters'
            msg += '\n'

        if self.out_urls != []:
            msg += 'Export results:\n'
            msg += '\n'.join(self.out_urls)
        else:
            msg += 'Export result: None'

        self.executor.cb(msg)

        return True