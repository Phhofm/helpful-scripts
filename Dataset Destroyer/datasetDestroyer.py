import configparser
import os
import cv2
import numpy as np
import ffmpeg
from random import randint, choice, shuffle
from tqdm import tqdm

import logging

logging.basicConfig(level=logging.DEBUG)

# Read config file
config = configparser.ConfigParser()
config.read('config.ini')

# Get config values
input_folder = config.get('main', 'input_folder')
output_folder = config.get('main', 'output_folder')
output_format = config.get('main', 'output_format')
degradations = config.get('main', 'degradations').split(',')
degradations_randomize = config.getboolean('main', 'randomize')
blur_algorithms = config.get('blur', 'algorithms').split(',')
blur_randomize = config.getboolean('blur', 'randomize')
blur_range = tuple(map(int, config.get('blur', 'range').split(',')))
noise_algorithms = config.get('noise', 'algorithms').split(',')
noise_randomize = config.getboolean('noise', 'randomize')
noise_range = tuple(map(int, config.get('noise', 'range').split(',')))
compression_algorithms = config.get('compression', 'algorithms').split(',')
compression_randomize = config.getboolean('compression', 'randomize')
jpeg_quality_range = tuple(map(int, config.get('compression', 'jpeg_quality_range').split(',')))
webp_quality_range = tuple(map(int, config.get('compression', 'webp_quality_range').split(',')))
h264_crf_level_range = tuple(map(int, config.get('compression', 'h264_crf_level_range').split(',')))
hevc_crf_level_range = tuple(map(int, config.get('compression', 'hevc_crf_level_range').split(',')))
size_factor = config.getfloat('scale', 'size_factor')
scale_algorithms = config.get('scale', 'algorithms').split(',')
down_up_scale_algorithms = config.get('scale', 'down_up_algorithms').split(',')
scale_randomize = config.getboolean('scale', 'randomize')
scale_range = tuple(map(float, config.get('scale', 'range').split(',')))
print_to_image = config.getboolean('main', 'print')


def print_text_to_image(image, text, order):
    return cv2.putText(image, f"{order}. {text}", (10, order * 50), cv2.FONT_HERSHEY_SIMPLEX, 1.25 * size_factor,
                       (255, 0, 0), 2, cv2.LINE_AA)


def apply_blur(image):
    text = ''
    # Choose blur algorithm
    if blur_randomize:
        algorithm = choice(blur_algorithms)
    else:
        algorithm = blur_algorithms[0]

    # Apply blur with chosen algorithm
    if algorithm == 'average':
        ksize = randint(*blur_range)
        image = cv2.blur(image, (ksize, ksize))
        text = f"{algorithm} ksize={ksize}"
    elif algorithm == 'gaussian':
        ksize = randint(*blur_range) | 1
        image = cv2.GaussianBlur(image, (ksize, ksize), 0)
        text = f"{algorithm} ksize={ksize}"
    elif algorithm == 'isotropic':
        # Apply isotropic blur using a Gaussian filter with the same standard deviation in both the x and y directions
        sigma = randint(*blur_range)
        ksize = 2 * int(4 * sigma + 0.5) + 1
        image = cv2.GaussianBlur(image, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)
        text = f"{algorithm} ksize={ksize} sigma={sigma}"
    elif algorithm == 'anisotropic':
        # Apply anisotropic blur using a Gaussian filter with different standard deviations in the x and y directions
        sigma_x = randint(*blur_range)
        sigma_y = randint(*blur_range)
        ksize_x = 2 * int(4 * sigma_x + 0.5) + 1
        ksize_y = 2 * int(4 * sigma_y + 0.5) + 1
        image = cv2.GaussianBlur(image, (ksize_x, ksize_y), sigmaX=sigma_x, sigmaY=sigma_y)
        text = f"{algorithm} sigma_x={sigma_x} sigma_y={sigma_y} ksize_x={ksize_x} ksize_y={ksize_y}"

    return image, text


def apply_noise(image):
    text = ''
    # Choose noise algorithm
    if noise_randomize:
        algorithm = choice(noise_algorithms)
    else:
        algorithm = noise_algorithms[0]

    # Apply noise with chosen algorithm
    if algorithm == 'uniform':
        intensity = randint(*noise_range)
        noise = np.random.uniform(-intensity, intensity, image.shape)
        image = cv2.add(image, noise.astype(image.dtype))
        text = f"{algorithm} intensity={intensity}"
    elif algorithm == 'gaussian':
        intensity = randint(*noise_range)
        noise = np.random.normal(0, intensity, image.shape)
        image = cv2.add(image, noise.astype(image.dtype))
        text = f"{algorithm} intensity={intensity}"
    elif algorithm == 'color':
        noise = np.zeros_like(image)
        m = (0, 0, 0)
        s = (randint(*noise_range), randint(*noise_range), randint(*noise_range))
        cv2.randn(noise, m, s)
        image += noise
        text = f"{algorithm} s={s}"
    elif algorithm == 'gray':
        gray_noise = np.zeros((image.shape[0], image.shape[1]), dtype=np.uint8)
        m = (0,)
        s = (randint(*noise_range),)
        cv2.randn(gray_noise, m, s)
        gray_noise = gray_noise[..., None]
        image += gray_noise
        text = f"{algorithm} s={s}"

    return image, text


def apply_compression(image):
    text = ''
    # Choose compression algorithm
    if compression_randomize:
        algorithm = choice(compression_algorithms)
    else:
        algorithm = compression_algorithms[0]

    # Apply compression with chosen algorithm
    if algorithm == 'jpeg':
        quality = randint(*jpeg_quality_range)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        result, encimg = cv2.imencode('.jpg', image, encode_param)
        image = cv2.imdecode(encimg, 1).copy()
        text = f"{algorithm} quality={quality}"
    elif algorithm == 'webp':
        quality = randint(*webp_quality_range)
        encode_param = [int(cv2.IMWRITE_WEBP_QUALITY), quality]
        result, encimg = cv2.imencode('.webp', image, encode_param)
        image = cv2.imdecode(encimg, 1).copy()
        text = f"{algorithm} quality={quality}"
    elif algorithm in ['h264', 'hevc', 'mpeg', 'mpeg2']:
        # Convert image to video format
        height, width, _ = image.shape
        codec = algorithm
        container = 'mpeg'
        codec = algorithm
        if algorithm == 'mpeg':
            codec = 'mpeg1video'
        elif algorithm == 'mpeg2':
            codec = 'mpeg2video'
        container = 'mpeg'

        # Get CRF level or bitrate from config
        if algorithm == 'h264':
            crf_level = randint(*h264_crf_level_range)
            output_args = {'crf': crf_level}
        elif algorithm == 'hevc':
            crf_level = randint(*hevc_crf_level_range)
            output_args = {'crf': crf_level, 'x265-params': 'log-level=0'}
        elif algorithm == 'mpeg':
            bitrate = config.get('compression', 'mpegbitrate')
            output_args = {'b': bitrate}
        elif algorithm == 'mpeg2':
            bitrate = config.get('compression', 'mpeg2bitrate')
            output_args = {'b': bitrate}
        else:
            output_args = {}

        # Encode image using ffmpeg
        process1 = (
            ffmpeg
            .input('pipe:', format='rawvideo', pix_fmt='bgr24', s=f'{width}x{height}')
            .output('pipe:', format=container, vcodec=codec, **output_args)
            .global_args('-loglevel', 'error')
            # .global_args('-movflags', 'frag_keyframe+empty_moov')
            .global_args('-max_muxing_queue_size', '300000')
            .run_async(pipe_stdin=True, pipe_stdout=True)
        )
        process1.stdin.write(image.tobytes())
        process1.stdin.close()

        # Decode compressed video back into image format using ffmpeg
        process2 = (
            ffmpeg
            .input('pipe:', format=container)
            .output('pipe:', format='rawvideo', pix_fmt='bgr24')
            .global_args('-loglevel', 'error')
            .run_async(pipe_stdin=True, pipe_stdout=True)
        )

        out, err = process2.communicate(input=process1.stdout.read())

        process1.wait()

        try:
            image = np.frombuffer(out, np.uint8).reshape([height, width, 3]).copy()
            first_arg = list(output_args.items())[0]
            text = f"{algorithm} {first_arg[0]}={first_arg[1]}"
        except ValueError as e:
            logging.error(f'Error reshaping output from ffmpeg: {e}')
            logging.error(f'Image dimensions: {width}x{height}')
            logging.error(f'ffmpeg stderr output: {err}')
            raise e

    return image, text


def apply_scale(image):
    text = ''
    # Calculate new size
    h, w = image.shape[:2]
    new_h = int(h * size_factor)
    new_w = int(w * size_factor)

    # Choose scale algorithm
    if scale_randomize:
        algorithm = choice(scale_algorithms)
    else:
        algorithm = scale_algorithms[0]

    interpolation_map = {
        'bicubic': cv2.INTER_CUBIC,
        'bilinear': cv2.INTER_LINEAR,
        'box': cv2.INTER_AREA,
        'nearest': cv2.INTER_NEAREST,
        'lanczos': cv2.INTER_LANCZOS4
    }

    if algorithm == 'down_up':
        if scale_randomize:
            algorithm1 = choice(down_up_scale_algorithms)
            algorithm2 = choice(down_up_scale_algorithms)
        else:
            algorithm1 = down_up_scale_algorithms[0]
            algorithm2 = down_up_scale_algorithms[-1]
        scale_factor = np.random.uniform(*scale_range)
        image = cv2.resize(image, (int(w * scale_factor), int(h * scale_factor)),
                           interpolation=interpolation_map[algorithm1])
        image = cv2.resize(image, (new_w, new_h), interpolation=interpolation_map[algorithm2])
        if print_to_image:
            text = f"{algorithm} scale1factor={scale_factor:.2f} scale1algorithm={algorithm1} scale2factor={size_factor/scale_factor:.2f} scale2algorithm={algorithm2}"
    else:
        image = cv2.resize(image, (new_w, new_h), interpolation=interpolation_map[algorithm])
        if print_to_image:
            text = f"{algorithm} size factor={size_factor}"

    return image, text


def process_image(image_path):
    image = cv2.imread(image_path)

    degradation_order = degradations.copy()
    all_text = []
    if degradations_randomize:
        shuffle(degradation_order)
    for order, degradation in enumerate(degradation_order, 1):
        if degradation == 'blur':
            image, text = apply_blur(image)
        elif degradation == 'noise':
            image, text = apply_noise(image)
        elif degradation == 'compression':
            image, text = apply_compression(image)
        elif degradation == 'scale':
            image, text = apply_scale(image)
        all_text.append(f"{degradation} {text}")

    if print_to_image:
        for order, text in enumerate(all_text, 1):
            image = print_text_to_image(image, text, order)

    output_path = os.path.join(output_folder, os.path.relpath(image_path, input_folder))
    output_path = os.path.splitext(output_path)[0] + '.' + output_format
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, image)


# Process images recursively
image_paths = []
for subdir, dirs, files in os.walk(input_folder):
    for file in files:
        image_paths.append(os.path.join(subdir, file))

for image_path in tqdm(image_paths):
    process_image(image_path)
