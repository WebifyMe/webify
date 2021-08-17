from dataclasses import dataclass, field
from .io_utils import process_file, save_yaml, read_yaml, data_name
from .md import build_markdown
from .notebook import process_notebook
from .jekyll import create_jekyll_home_header, create_jekyll_file
import typing as th
import os


@dataclass
class Builder:
    base_url: str
    repo_full_name: str
    assets_dir: str = 'assets'
    markdown_extensions: th.Optional[th.Iterable[str]] = (
        'md_in_html', 'codehilite', 'fenced_code', 'tables', 'attr_list')
    checked_indices: set = field(default_factory=set)

    def build_person(self, person, assets_src_dir=None, assets_target_dir=None):
        assert isinstance(person, dict), \
            f'person objects, are expected to be dictionaries, {type(person)} provided instead!'
        image = person.get('image', None)
        # build contact links
        for idx, contact_info in enumerate(person.get('contact', [])):
            person['contact'][idx] = self.build_link(contact_info, None)
            if 'github.com' in contact_info['link']:
                # if no image was provided use person github profile picture instead
                image = f"{contact_info['link']}.png"
        if 'image' in person:
            # copy person's static profile image into assets
            src = person['image'] if assets_src_dir is None else f'{assets_src_dir}/{person["image"]}'
            target = person['image'] if assets_target_dir is None else f'{assets_target_dir}/{person["image"]}'
            image = process_file(src, target, baseurl=self.base_url)
        else:
            for contact_info in person.get('contact', []):
                if 'github.com' in contact_info['link']:
                    # if no image was provided use person github profile picture instead
                    image = f"{contact_info['link']}.png"
                    break
        if image:
            person['image'] = image

        # process bio markdown
        if 'bio' in person:
            person['bio'] = build_markdown(builder=self, raw=person['bio'], extensions=self.markdown_extensions)
        return person

    def build_link(self, link, image_key=None, assets_src_dir=None, assets_target_dir=None):
        assets_target_dir = self.assets_dir if assets_target_dir is None else assets_target_dir
        if 'notebook' in link:
            link = process_notebook(builder=self, link=link)  # in case some data was added to link descriptor later
        elif 'kind' in link and link['kind'] == 'person':
            link = self.build_person(link, assets_src_dir=assets_src_dir, assets_target_dir=assets_target_dir)
        elif 'index' in link:
            index = self.build_index(index_file=link['index'])
            if 'text' not in link:
                if 'title' in index:
                    link['text'] = index['title']
                elif 'header' in index and 'title' in index['header']:
                    link['text'] = index['header']['title']
            if 'description' not in link and 'header' in index and 'description' in index['header']:
                link['description'] = index['header']['description']
            link['link'] = f'{self.base_url}/{link["index"]}.html' if not link["index"].endswith('index') else \
                f'{self.base_url}/{"/".join(link["index"].split("/")[:-1])}'
        elif 'pdf' in link:
            file_path = process_file(link['pdf'], link['pdf'], target_dir='assets', baseurl=self.base_url)
            if file_path:
                link['pdf'] = file_path
        else:
            # processing markdown syntax
            if 'description' in link:
                link['description'] = build_markdown(builder=self, raw=link['description'],
                                                     extensions=self.markdown_extensions)
        return link

    def build_object(self, obj, image_key=None, assets_src_dir=None, assets_target_dir=None):
        """Process the self replicating structure of objects in `index.yml`
        """
        assets_target_dir = self.assets_dir if assets_target_dir is None else assets_target_dir
        # objects are either have descriptors or a list of link objects
        content = obj if isinstance(obj, dict) and 'content' not in obj else (
            obj.get('content', obj) if isinstance(obj, dict) else obj)

        # building object content
        if isinstance(content, list):
            # if object is a list of other objects
            for idx, item in enumerate(content):
                if 'kind' in obj and obj['kind'] == 'people':
                    item['kind'] = 'person'
                if 'kind' in obj and obj['kind'] == 'chapters':
                    content[idx] = self.build_index(item)
                else:
                    content[idx] = self.build_link(item, assets_src_dir=assets_src_dir,
                                                   assets_target_dir=assets_target_dir)
        elif isinstance(obj, dict) and 'content' in obj:
            for key, value in obj.items():
                if key in ['label']:
                    continue
                if key == 'content':
                    content = self.build_object(
                        obj['content'], image_key, assets_src_dir=assets_src_dir, assets_target_dir=assets_target_dir)
                    continue
                obj[key] = self.build_object(
                    value, image_key, assets_src_dir=assets_src_dir, assets_target_dir=assets_target_dir)
        elif isinstance(obj, str):
            return build_markdown(builder=self, raw=obj, extensions=self.markdown_extensions)
        else:
            return obj
        # processing markdown
        if 'content' in obj:
            obj['content'] = content
        else:
            obj = content

        # building object (background) image
        if image_key is not None and image_key in obj:
            target_path = process_file(obj[image_key], obj[image_key], src_dir=assets_src_dir,
                                       target_dir=assets_target_dir,
                                       baseurl=self.base_url)
            if target_path:
                obj[image_key] = target_path
        return obj

    def build_index(self, index: dict = None, index_file: str = None, target_data_file: str = None, index_type='index'):
        """Process the self replicating structure of `index.yml` and look for notebook links and render them.
        """
        assert index_file is not None or index is not None, f'Either index or index_file should be specified!'
        if index is None:
            assert os.path.isfile(f'{index_file}.yml'), \
                f"{index_type.capitalize()} file {f'{index_file}.yml'} could not be found!"
            index = read_yaml(f'{index_file}.yml')
            if index_file in self.checked_indices:
                return index
            print(f'Processing {index_type}', index_file)
            self.checked_indices.add(index_file)

        assert isinstance(index, dict), \
            f'index is supposed to be an object, got {type(index)}'
        if 'title' not in index and 'header' in index and 'title' in index['header']:
            index['title'] = index['header']['title']
        index['title'] = index.get('title', index_type.capitalize())
        for key, value in index.items():
            if key in ['title']:
                continue
            index[key] = self.build_object(value, image_key='background')

        if index_file is not None:
            # save data file
            save_yaml(
                index,
                f'_data/{data_name(index_file, index_type)}.yml' if target_data_file is None else target_data_file
            )
            # create and save html file
            if index_type == 'index':
                create_jekyll_file(f'{index_file}.html', create_jekyll_home_header(data_name(index_file, index_type)))

        return index