import numpy as np

from src.spatial_index.common_utils import Region, binary_search_less_max, get_nearest_none, sigmoid
from src.spatial_index.geohash_utils import Geohash


class SBRIN:
    def __init__(self, meta_page=None, regular_pages=None):
        # meta page
        # version: 序号偏移
        # pages_per_range: pages偏移 = (itemoffset - 1) * pagesperrange
        # last_revmap_page: 改动：max_length长度的整型geohash
        # threshold_number: 新增：blk range 分裂的数量阈值
        # threshold_length: 新增：blk range 分裂的geohash长度阈值
        # geohash: 新增：max_length = geohash.sum_bits
        # size: 优化计算所需：blk size - 1
        self.meta_page = meta_page
        # revmap pages
        # 忽略revmap，pages找blk range的过程，通过itemoffset和pagesperrange直接完成
        # self.revmap_pages = revmap_pages
        # regular pages
        # itemoffet: 序号偏移
        # blknum: pages偏移 = (itemoffset - 1) * pagesperrange
        # value: 改动：max_length长度的整型geohash
        # length: 新增：blk range geohash的实际length
        # number: 新增：blk range的数据量
        # model: 新增：learned indices
        # scope: 优化计算所需：BRIN-Spatial有，blk range的scope
        # key: 优化计算所需：blk range的索引key范围=[blknum * block_size, blknum * block_size + number]
        self.regular_pages = regular_pages

    @staticmethod
    def init_by_dict(d: dict):
        return SBRIN(meta_page=d['meta_page'],
                     regular_pages=d['regular_pages'])

    def build(self, data_list, threshold_number, threshold_length,
              region, data_precision, block_size):
        """
        构建SBRIN
        1. 初始化第一个blk range
        2. 用堆栈存储blk range，对每个blk range进行分裂
        3. 把不超过的blk range加入结果list，加入的时候顺序为[左上，右下，左上，右上]的逆序，因为堆栈
        4. 从结果list创建SBRIN
        5. 重构数据，每个blk range对应threshold_number的数据空间，移到外面做
        """
        # 1. 初始化第一个blk range
        N = len(data_list)
        tmp_stack = [(0, 0, N, (0, N - 1), region)]
        result_list = []
        geohash = Geohash.init_by_precision(data_precision=data_precision, region=region)
        # 2. 用堆栈存储blk range，对每个blk range进行分裂
        while len(tmp_stack):
            cur = tmp_stack.pop(-1)
            # 如果number超过threshold_number或且length不超过了threshold_length则分裂
            if cur[2] >= threshold_number and cur[1] < threshold_length:
                child_region = cur[4].split()
                left_key = cur[3][0]
                right_key = cur[3][1]
                tmp_left_key = left_key
                child_list = [None] * 4
                # 1. length生成
                length = cur[1] + 2
                r_bound = cur[0] + (0 << geohash.sum_bits - length)
                for i in range(4):
                    # 2. value生成
                    value = r_bound
                    # 3. 数据继承：number生成
                    # 计算right bound
                    r_bound = cur[0] + (i + 1 << geohash.sum_bits - length)
                    # 找到r_bound对应的key
                    tmp_right_key = binary_search_less_max(data_list, 2, r_bound, tmp_left_key, right_key)
                    child_list[i] = (value, length, tmp_right_key - tmp_left_key + 1,
                                     (tmp_left_key, tmp_right_key), child_region[i])
                    tmp_left_key = tmp_right_key + 1
                tmp_stack.extend(child_list[::-1])  # 倒着放入init中，保持顺序
            else:
                # 3. 把不超过的blk range加入结果list，加入的时候顺序为[左上，右下，左上，右上]的逆序，因为堆栈
                result_list.append(cur)
        # 4. 从结果list创建SBRIN
        # 100为block_size
        pages_per_range = threshold_number // block_size
        # last_revmap_page理论上是第一个regular_page磁盘位置-1
        self.meta_page = MetaPage(version=1, pages_per_range=pages_per_range, last_revmap_page=0,
                                  threshold_number=threshold_number, threshold_length=threshold_length,
                                  geohash=geohash,
                                  max_length=max([result[1] for result in result_list]),
                                  size=len(result_list) - 1)
        self.regular_pages = [RegularPage(itemoffset=i + 1,
                                          blknum=i * pages_per_range,
                                          value=result_list[i][0],
                                          length=result_list[i][1],
                                          number=result_list[i][2],
                                          model=None,
                                          scope=Region.up_right_less_region(result_list[i][4],
                                                                            pow(10, -data_precision - 1)),
                                          key=result_list[i][3],
                                          next_value=None)
                              for i in range(len(result_list))]
        for i in range(len(result_list) - 1):
            self.regular_pages[i].next_value = result_list[i + 1][0]
        self.regular_pages[-1].next_value = 1 << self.meta_page.geohash.sum_bits
        # revmap_pages理论上要记录每个regular的磁盘位置
        # 5. 重构数据，每个blk range对应threshold_number的数据空间，移到外面做
        # 移到外面做

    def reconstruct_data(self, data_list):
        """
        把属于br的数据存储在br的范围内
        """
        result_data_list = []
        for regular_page in self.regular_pages:
            result_data_list.extend(data_list[regular_page.key[0]: regular_page.key[1] + 1])
            diff_length = self.meta_page.threshold_number - regular_page.number
            result_data_list.extend([None] * diff_length)
            regular_page.key = [self.meta_page.threshold_number * (regular_page.itemoffset - 1),
                                self.meta_page.threshold_number * (
                                        regular_page.itemoffset - 1) + regular_page.number - 1]
        return result_data_list

    def reconstruct_data_old(self, data_list):
        """
        把数据存在predict的地方，如果pre已有数据：
        1. pre处数据的geohash==数据本身的geohash，说明数据重复，则找到离pre最近的[pre-maxerr, pre-minerr]范围内的None来存储
        2. pre处数据的geohash!=数据本身的geohash，说明本该属于数据的位置被其他数据占用了，为了保持有序，找None的过程只往一边走
        存在问题：这种重构相当于在存储数据的时候依旧保持数据分布的稀疏性，但是密集的地方后续往往更加密集，导致这些地方的数据存储位置更加紧张
        这个问题往往在大数据量或误差大或分布不均匀的br更容易出现，即最后"超出边界"的报错
        """
        result_data_list = [None] * (self.meta_page.size + 1) * self.meta_page.threshold_number
        for regular_page in self.regular_pages:
            regular_page.model.output_min = self.meta_page.threshold_number * (regular_page.itemoffset - 1)
            regular_page.model.output_max = self.meta_page.threshold_number * regular_page.itemoffset - 1
            for i in range(regular_page.key[0], regular_page.key[1] + 1):
                pre = round(regular_page.model.predict(data_list[i][2]))
                if result_data_list[pre] is None:
                    result_data_list[pre] = data_list[i]
                else:
                    # 重复数据处理：写入误差范围内离pre最近的None里
                    if result_data_list[pre][2] == data_list[i][2]:
                        l_bound = max(round(pre - regular_page.model.max_err), regular_page.model.output_min)
                        r_bound = min(round(pre - regular_page.model.min_err), regular_page.model.output_max)
                    else:  # 非重复数据，但是整型部分重复，或被重复数据取代了位置
                        if result_data_list[pre][2] > data_list[i][2]:
                            l_bound = max(round(pre - regular_page.model.max_err), regular_page.model.output_min)
                            r_bound = pre
                        else:
                            l_bound = pre
                            r_bound = min(round(pre - regular_page.model.min_err), regular_page.model.output_max)
                    key = get_nearest_none(result_data_list, pre, l_bound, r_bound)
                    if key is None:
                        # 超出边界是因为大量的数据相互占用导致误差放大
                        print("超出边界")
                    else:
                        result_data_list[key] = data_list[i]
        return result_data_list

    def point_query(self, point):
        """
        根据geohash找到所在的blk range的key
        1. 计算geohash对应到blk的geohash_int
        2. 找到比geohash_int小的最大值即为geohash所在的blk range
        """
        return self.binary_search_less_max(point, 0, self.meta_page.size)

    def range_query_old(self, point1, point2, window):
        """
        根据geohash1/geohash2找到之间所有blk range以及blk range和window的相交关系
        1. 使用point_query查找geohash1/geohash2所在blk range
        2. 返回blk range1和blk range2之间的所有blk range，以及他们和window的的包含关系
        TODO: intersect函数还可以改进，改为能判断window对于region的上下左右关系
        """
        i = self.binary_search_less_max(point1, 0, self.meta_page.size)
        j = self.binary_search_less_max(point2, i, self.meta_page.size)
        if i == j:
            return [((3, None), self.regular_pages[i])]
        else:
            return [(window.intersect(self.regular_pages[k].scope), self.regular_pages[k]) for k in range(i, j - 1)]

    def range_query(self, point1, point2):
        """
        根据geohash1/geohash2找到之间所有blk range的key以及和window的位置关系
        1. 通过geohash_int1/geohash_int2找到window对应的所有org_geohash和对应window的position
        2. 通过前缀匹配过滤org_geohash来找到tgt_geohash
        3. 根据tgt_geohash分组并合并position
        """
        # 1. 通过geohash_int1/geohash_int2找到window对应的所有org_geohash和对应window的position
        br_key1 = self.binary_search_less_max(point1, 0, self.meta_page.size)
        br_key2 = self.binary_search_less_max(point2, br_key1, self.meta_page.size)
        if br_key1 == br_key2:
            return {br_key1: 15}
        else:
            org_geohash_list = self.meta_page.geohash.ranges_by_int(point1, point2, self.meta_page.max_length)
            # 2. 通过前缀匹配过滤org_geohash来找到tgt_geohash
            # 3. 根据tgt_geohash分组并合并position
            size = len(org_geohash_list) - 1
            i = 1
            tgt_geohash_dict = {br_key1: org_geohash_list[0][1],
                                br_key2: org_geohash_list[-1][1]}
            while i < size:
                if self.regular_pages[br_key1].value > org_geohash_list[i][0]:
                    tgt_geohash_dict[br_key1 - 1] = tgt_geohash_dict.get(br_key1 - 1, 0) | org_geohash_list[i][1]
                    i += 1
                else:
                    br_key1 += 1
            return tgt_geohash_dict
            # 前缀匹配太慢：时间复杂度=O(len(window对应的geohash个数)*(j-i))

    def knn_query(self, point1, point2, point3):
        """
        根据geohash1/geohash2找到之间所有blk range的key以及和window的位置关系，并基于和point3距离排序
        1. 通过geohash_int1/geohash_int2找到window对应的所有org_geohash和对应window的position
        2. 通过前缀匹配过滤org_geohash来找到tgt_geohash
        3. 根据tgt_geohash分组并合并position
        4. 计算每个tgt_geohash和point3的距离，并进行降序排序
        """
        # 1. 通过geohash_int1/geohash_int2找到window对应的所有org_geohash和对应window的position
        br_key1 = self.binary_search_less_max(point1, 0, self.meta_page.size)
        br_key2 = self.binary_search_less_max(point2, br_key1, self.meta_page.size)
        if br_key1 == br_key2:
            return [[br_key1, 15, 0]]
        else:
            org_geohash_list = self.meta_page.geohash.ranges_by_int(point1, point2, self.meta_page.max_length)
            # 2. 通过前缀匹配过滤org_geohash来找到tgt_geohash
            # 3. 根据tgt_geohash分组并合并position
            size = len(org_geohash_list) - 1
            i = 1
            tgt_geohash_dict = {br_key1: org_geohash_list[0][1],
                                br_key2: org_geohash_list[-1][1]}
            while i < size:
                if self.regular_pages[br_key1].value > org_geohash_list[i][0]:
                    tgt_geohash_dict[br_key1 - 1] = tgt_geohash_dict.get(br_key1 - 1, 0) | org_geohash_list[i][1]
                    i += 1
                else:
                    br_key1 += 1
            # 4. 计算每个tgt_geohash和point3的距离，并进行降序排序
            return sorted([[tgt_geohash,
                            tgt_geohash_dict[tgt_geohash],
                            self.regular_pages[tgt_geohash].scope.get_min_distance_pow_by_point_list(point3)]
                           for tgt_geohash in tgt_geohash_dict], key=lambda x: x[2])

    def binary_search_less_max(self, x, left, right):
        """
        二分查找比x小的最大值
        优化: 循环->二分:15->1
        """
        while left <= right:
            mid = (left + right) // 2
            if self.regular_pages[mid].value == x:
                return mid
            elif self.regular_pages[mid].value < x:
                left = mid + 1
            else:
                right = mid - 1
        return right


class MetaPage:
    def __init__(self, version, pages_per_range, last_revmap_page,
                 threshold_number, threshold_length, geohash, max_length, size):
        # BRIN
        self.version = version
        self.pages_per_range = pages_per_range
        self.last_revmap_page = last_revmap_page
        # SBRIN
        self.threshold_number = threshold_number
        self.threshold_length = threshold_length
        self.geohash = geohash
        self.max_length = max_length
        # For compute
        self.size = size

    @staticmethod
    def init_by_dict(d: dict):
        return MetaPage(version=d['version'],
                        pages_per_range=d['pages_per_range'],
                        last_revmap_page=d['last_revmap_page'],
                        threshold_number=d['threshold_number'],
                        threshold_length=d['threshold_length'],
                        geohash=d['geohash'],
                        max_length=d['max_length'],
                        size=d['size'])


class RegularPage:
    def __init__(self, itemoffset, blknum, value, length, number, model, scope, key, next_value):
        # BRIN
        self.itemoffset = itemoffset
        self.blknum = blknum
        self.value = value
        # SBRIN
        self.length = length
        self.number = number
        self.model = model
        # For compute
        self.scope = scope
        self.key = key
        self.next_value = next_value

    @staticmethod
    def init_by_dict(d: dict):
        return RegularPage(itemoffset=d['itemoffset'],
                           blknum=d['blknum'],
                           value=d['value'],
                           length=d['length'],
                           number=d['number'],
                           model=d['model'],
                           scope=d['scope'],
                           key=d['key'],
                           next_value=d['next_value'])

    def model_predict(self, x):
        x = int(self.model.predict((x - self.value) / (self.next_value - self.value) - 0.5) * self.number)
        if x <= 0:
            return self.key[0]
        elif x >= self.number:
            return self.key[1]
        return self.key[0] + x


class AbstractNN:
    def __init__(self, weights, hl_nums, min_err, max_err):
        self.weights = weights
        self.hl_nums = hl_nums
        self.min_err = min_err
        self.max_err = max_err

    # @memoize
    # model.predict有小偏差，可能是exp的e和elu的e不一致
    def predict(self, x):
        for i in range(self.hl_nums):
            x = sigmoid(x * self.weights[i * 2] + self.weights[i * 2 + 1])
        return (x * self.weights[-2] + self.weights[-1])[0, 0]

    @staticmethod
    def init_by_dict(d: dict):
        weights_mat = [np.mat(weight) for weight in d['weights']]
        return AbstractNN(weights_mat, d['hl_nums'], d['min_err'], d['max_err'])
