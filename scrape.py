import argparse
import asyncio
import itertools
import json
import os
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from random import choice
from typing import Any, Iterable, List, Set, Tuple

import aiofiles
import aiohttp
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras.applications import EfficientNetB0
from tensorflow.keras.utils import image_dataset_from_directory
from tensorflow.python.ops.numpy_ops import np_config

np_config.enable_numpy_behavior()


def batch(iterable: Iterable, batch_size: int) -> List[List[Any]]:
    """
    Split an iterable into iterables of a given batch sizes. Will pad missing values as None.
    """
    args = [iter(iterable)] * batch_size
    return [
        [item for item in chunk if item is not None]
        for chunk in itertools.zip_longest(*args, fillvalue=None)
    ]


def download(
    urls: List[str], filenames: List[str], retry: int = 2
) -> Set[Tuple[str, str]]:
    async def download_file(url: str, dst: str):
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=True)
        ) as session:
            response = await session.get(url)
            assert response.status == 200, f"Received response status {response.status}"
            data = await response.read()

        parent_dirs = os.path.dirname(dst)
        if not os.path.exists(parent_dirs):
            os.makedirs(parent_dirs)

        async with aiofiles.open(dst, "wb") as outfile:
            await outfile.write(data)
        return url, dst

    async def _gather(_urls: List[str], _file_names: List[str]):
        download_futures = [
            download_file(url, dst) for url, dst in zip(_urls, _file_names)
        ]
        return await asyncio.gather(*download_futures, return_exceptions=True)

    results = asyncio.run(_gather(urls, filenames))
    success = set()
    failed = set()
    for item in results:
        if isinstance(item, Exception):
            continue
        success.add(item)

    failed = set(zip(urls, filenames)) - success

    if failed and retry > 0:
        urls, dsts = tuple(zip(*failed))
        failed = download(urls, dsts, retry=retry - 1)

    return failed


def gather(urls, params):
    async def req(url, params):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector()) as session:
            response = await session.get(url, params=params)
            assert response.status == 200, f"Received status code {response.status}"
            if response.content_type == "application/json":
                return await response.json()
            else:
                return await response.read()

    async def _gather(_urls, _params):
        load_futures = [req(url, param) for url, param in zip(_urls, _params)]
        return await asyncio.gather(*load_futures, return_exceptions=True)

    data = asyncio.run(_gather(urls, params))
    errors = []
    results = []
    for url, param, item in zip(urls, params, data):
        if isinstance(item, Exception):
            errors.append((url, param, item))
        else:
            results.append(item)
    return results, errors


# I only need to output as ndjson as reading it is still json
class NDJSONEncoder(json.JSONEncoder):
    def encode(self, obj, *args, **kwargs):
        lines = []
        for each in obj:
            line = super(NDJSONEncoder, self).encode(each, *args, **kwargs)
            lines.append(line)
        return "\n".join(lines)


def ndumps(*args, **kwargs):
    kwargs["cls"] = NDJSONEncoder
    return json.dumps(*args, **kwargs)


def load_ndjson(file_name):
    with open(file_name) as file:
        while line := file.readline():
            yield json.loads(line)


class TagHTMLParser(HTMLParser):
    """
    Each listing html looks like this
    <div id="taglist" class="grid">
    <div class="taglist-tagmain">
        <span class="taglist-name">
            <a class="sfw" href="https://wallhaven.cc/tag/141835" original-title="2PL">2PL</a>
        </span>
    """

    def __init__(self, *, convert_charrefs: bool = True) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self.within_name_span = False
        self.tags = {}

    def handle_starttag(self, tag, attrs):
        save_tag = False
        if tag == "span":
            if any((value == ("class", "taglist-name") for value in attrs)):
                self.within_name_span = True
        elif self.within_name_span and tag == "a":
            for attr, value in attrs:
                if attr == "class" and value == "sfw":
                    save_tag = True
                if attr == "href":
                    _id = int(value.split("/")[-1])
                if attr == "original-title" or attr == "title":
                    title = value

        if save_tag:
            self.tags[_id] = title

    def handle_endtag(self, tag):
        if tag == "span":
            self.within_name_span = False


class Scrapper:
    def __init__(self):
        self.category_ids = (
            24,  # Architecture
            25,  # Digital
            27,  # Traditional
            40,  # Animals
            41,  # Landscapes
            42,  # Plants
            43,  # Cities
            45,  # Space
            46,  # Other
            53,  # Aircraft
            54,  # Cars and Motorcycles
            55,  # Ships
            56,  # Spacecrafts
            57,  # Trains
            58,  # History
            60,  # Military & Weapons
        )
        self.parser = TagHTMLParser()
        self.tags = dict()
        self.output_file = "tags.ndjson"

    @staticmethod
    def url(tag_id):
        return f"https://wallhaven.cc/tags/tagged/{tag_id}"

    def to_file(self):
        data = []
        for _id, title in self.tags.items():
            title = title.strip()
            if not title.islower() or not title.isalpha():
                continue
            data.append({"id": _id, "title": title})

        with open(self.output_file, "w") as file:
            file.write(ndumps(data))

    def __call__(self):
        # I don't think I'll get rate limited @ 9 page reqs
        urls = []
        params = []
        for _id in self.category_ids:
            urls.append(self.url(_id))
            params.append({})

        data, err = gather(urls, params)

        for resp in data:
            html = resp.decode()
            self.parser.feed(html)
            self.tags.update(self.parser.tags)
        self.to_file()


@dataclass
class ImageEntry:
    url: str = ""
    tag_ids: set[int] = field(default_factory=set)


class Crawler:
    search_url = "https://wallhaven.cc/api/v1/search"
    search_colors = [
        None,
        "660000",
        "990000",
        "cc0000",
        "cc3333",
        "ea4c88",
        "993399",
        "663399",
        "333399",
        "0066cc",
        "0099cc",
        "66cccc",
        "77cc33",
        "669900",
        "336600",
        "666600",
        "999900",
        "cccc33",
        "ffff00",
        "ffcc33",
        "ff9900",
        "ff6600",
        "cc6633",
        "996633",
        "663300",
        "000000",
        "999999",
        "cccccc",
        "ffffff",
        "424153",
    ]
    base_search_params = {
        "categories": 100,
        "purity": 100,
        "resolutions": "1920x1080",
        "sorting": "relevance",
    }

    def __init__(self) -> None:
        self.tag_ids = [1]
        self.images = defaultdict(ImageEntry)
        self.output_file = "images.ndjson"
        self.tags_file = "tags.ndjson"

    def __call__(self):
        self.tag_counts = defaultdict(lambda: 0)
        for obj in load_ndjson(self.tags_file):
            tag_id = obj["id"]
            print(f"Searching for tag {tag_id}")
            urls = [self.search_url]
            params = [dict(**self.base_search_params, q=f"id:{tag_id}")]
            for color in self.search_colors:
                urls.append(self.search_url)
                params.append(
                    dict(**self.base_search_params, q=f"id:{tag_id}", colors=color)
                )

            urls = batch(urls, 10)
            params = batch(params, 10)

            for batch_urls, batch_params in zip(urls, params):
                data, err = gather(batch_urls, batch_params)
                print(f"Errored - {len(err)}")

                for resp in data:
                    if resp is None:
                        continue
                    for entry in resp.get("data", []):
                        _id = entry["id"]
                        url = entry["thumbs"]["small"]

                        self.images[_id].url = url
                        self.images[_id].tag_ids.add(tag_id)
                        self.tag_counts[tag_id] += 1
                time.sleep(20)

        self.to_file()

    def to_file(self):
        data = []
        for _id, entry in self.images.items():
            tag_ids = list(filter(lambda x: self.tag_counts[x] >= 100, entry.tag_ids))
            if not tag_ids:
                continue
            data.append({"id": _id, "url": entry.url, "tag_ids": tag_ids})

        with open(self.output_file, "w") as file:
            file.write(ndumps(data))


class Downloader:
    def __init__(self) -> None:
        self.main_dir = os.path.join(os.getcwd(), "dataset")
        if os.path.exists(self.main_dir):
            shutil.rmtree(self.main_dir)
        os.makedirs(self.main_dir)

        self.tags = {}
        for tag in load_ndjson("tags.ndjson"):
            _id = tag["id"]
            self.tags[_id] = tag["title"]

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        src_urls = []
        dst_paths = []
        for image in load_ndjson("images.ndjson"):
            _id = image["id"]
            tag_ids = image["tag_ids"]
            url = image["url"]
            tag_id = choice(tag_ids)
            tag_name = self.tags[tag_id]

            file_type = url.split(".")[-1]
            filename = f"{_id}.{file_type}"
            path = os.path.join(self.main_dir, tag_name, filename)
            src_urls.append(url)
            dst_paths.append(path)

        url_batches = batch(src_urls, 50)
        dst_batches = batch(dst_paths, 50)

        for urls, paths in zip(url_batches, dst_batches):
            errored = download(urls, paths)


class Trainer:
    def __init__(self):
        img_size = 224

        self.train_dataset, self.val_dataset = image_dataset_from_directory(
            "dataset",
            image_size=(img_size, img_size),
            validation_split=0.1,
            subset="both",
            seed=2,
            label_mode="categorical",
        )
        n_classes = len(self.train_dataset.class_names)

        with open("class_names.txt", "w") as fobj:
            for name in self.train_dataset.class_names:
                fobj.write(f"{name}\n")

        self.model = self.build_model(img_size, n_classes)

    @staticmethod
    def build_model(img_size, num_classes):
        inputs = layers.Input(shape=(img_size, img_size, 3))

        model = EfficientNetB0(
            include_top=False, input_tensor=inputs, weights="imagenet"
        )

        model.trainable = False

        x = layers.GlobalAveragePooling2D(name="avg_pool")(model.output)
        x = layers.BatchNormalization()(x)

        top_dropout_rate = 0.2
        x = layers.Dropout(top_dropout_rate, name="top_dropout")(x)
        outputs = layers.Dense(num_classes, activation="softmax", name="pred")(x)

        model = tf.keras.Model(inputs, outputs, name="EfficientNet")
        optimizer = tf.keras.optimizers.Adam(learning_rate=1e-2)
        model.compile(
            optimizer=optimizer, loss="categorical_crossentropy", metrics=["accuracy"]
        )
        return model

    @staticmethod
    def unfreeze_model(model):
        for layer in model.layers[-20:]:
            if not isinstance(layer, layers.BatchNormalization):
                layer.trainable = True

        optimizer = tf.keras.optimizers.Adam(learning_rate=1e-4)
        model.compile(
            optimizer=optimizer, loss="categorical_crossentropy", metrics=["accuracy"]
        )

    @staticmethod
    def plot_hist(hist, filename):
        plt.clf()
        plt.plot(hist.history["accuracy"])
        plt.plot(hist.history["val_accuracy"])
        plt.title("model accuracy")
        plt.ylabel("accuracy")
        plt.xlabel("epoch")
        plt.legend(["train", "validation"], loc="upper left")
        plt.savefig(filename)

    def plot_validation(self):
        for image_batch, label_batch in self.val_dataset.take(1):
            predictions = self.model.predict_on_batch(image_batch)
            plt.figure(figsize=(13, 8))
            for i in range(9):
                ax = plt.subplot(3, 3, i + 1)
                plt.imshow(image_batch[i].astype("uint8"))
                pred = predictions[i]
                classes = []
                conf = []
                for _ in range(5):
                    ix = pred.argmax()
                    classes.append(self.val_dataset.class_names[ix])
                    conf.append(pred[ix])
                    pred = np.delete(pred, ix)

                ix = label_batch[i].numpy().argmax()
                plt.title(self.val_dataset.class_names[ix])
                label_scores = (
                    f"{label} - {score:.6f} " for label, score in zip(classes, conf)
                )
                ax.text(
                    3,
                    2,
                    "\n".join(label_scores),
                    verticalalignment="top",
                    horizontalalignment="right",
                )
                plt.axis("off")
            plt.savefig("results/validation1.png", bbox_inches="tight")

    def __call__(self):
        epochs = 20
        hist = self.model.fit(
            self.train_dataset,
            epochs=epochs,
            validation_data=self.val_dataset,
            verbose=2,
        )
        self.plot_hist(hist, "results/top_train.png")

        self.unfreeze_model(self.model)
        epochs = 10
        hist = self.model.fit(
            self.train_dataset,
            epochs=epochs,
            validation_data=self.val_dataset,
            verbose=2,
        )
        self.plot_hist(hist, "results/unfreeze_train.png")

        # TODO: Busted  for EfficientNet in new versions https://github.com/keras-team/keras/issues/17199
        #     A PR with a fix is merged but not on official release, use the nightly build as a workaround
        self.model.save("model")
        self.plot_validation()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute training tasks.")
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Collect image tags and output to tags.ndjson",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="Collect wallhaven image entries and output to images.ndjson",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download images into a local dataset structure",
    )
    parser.add_argument(
        "--train",
        action="store_true",
        help="Train classification model from local dataset",
    )
    args = parser.parse_args()

    if args.scrape:
        tag_scraper = Scrapper()
        tag_scraper()
    elif args.crawl:
        img_crawler = Crawler()
        img_crawler()
    elif args.download:
        img_downloader = Downloader()
        img_downloader()
    elif args.train:
        trainer = Trainer()
        trainer()
